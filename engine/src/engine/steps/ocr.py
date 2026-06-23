"""ocr step — third OCR witness via a vision model on the source PDF scan.

Faithful port of the top-level ``ocr.py``: render each PDF page to an image, transcribe it with a
vision model, and stitch the per-page results into ``copy3`` text + a page map — the names
``reconcile`` reads. The mechanics (page-range, resume via a per-page progress dir, sequential /
thread-pool workers, ``[2, 8, 16]`` retry backoff, ``_stitch_pages``) are book/language-neutral
and ported ~verbatim. ``_stitch_pages`` is pure given the per-page texts → unit-tested directly.

The book/language opinions leave the code:

  - the source PDF is a per-book input at ``books/<id>/scans/<manifest.scan.pdf>`` (``ws.scans``, D7);
  - the model ids come from ``manifest.ocr.models`` — no baked frontier default (D3/BR-010);
  - the prompt is the book-neutral ``ocr`` template rendered with the book/language context (D2/BR-008).

Three seams are injectable (D1/BR-009), defaulting to the real backends so the property /
separability tiers run offline: ``PageRenderer`` (PyMuPDF render + page count), ``OcrBackend`` (the
vision call). The ``⟨PAGE:N⟩`` / ``[BLANK]`` / ``[OCR_ERROR]`` protocol constants are single-sourced
in ``contracts.markers`` so the prompt template, the stitcher, and ``reconcile`` cannot drift (F6).

Resume scaffolding (the per-page progress dir) is transient state → ``ws.state``; the final
``copy3`` text + page map are pipeline inputs → ``ws.data`` (the live ``ocr`` parks progress beside
the output in ``data/``; routing it to ``state/`` aligns with the engine's area semantics — a
two-way door).
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Protocol

from ..config.models import ResolvedConfig
from ..contracts.markers import (
    PAGE_MARKER_TEMPLATE,
    SENTINEL_BLANK,
    SENTINEL_OCR_ERROR_PREFIX,
)
from ..errors import BackendError, MissingInputError
from ..lang.base import LanguagePlugin
from ..paths import BookWorkspace
from ..prompts.templating import PromptTemplate, build_prompt_context
from ..util.jsonio import atomic_write_json, atomic_write_text, read_json

# Output filenames reconcile reads: pro → copy3_raw.txt (quality witness), flash → copy3_flash.txt.
_OUTPUT_NAMES = {"pro": "copy3_raw.txt", "flash": "copy3_flash.txt"}

# Scan-render tuning — code defaults (promotable to the manifest ocr block if a book needs them).
_DEFAULT_DPI = 200
_JPEG_QUALITY = 85

# Retry backoff between transcription attempts (seconds) + inter-page politeness delay, verbatim
# from live ocr. Module constants so tests can drop them to zero for speed.
_RETRY_BACKOFF = (2, 8, 16)
_PAGE_DELAY = 0.2


# --- injectable seams (D1/BR-009) ------------------------------------------------------ #

class PageRenderer(Protocol):
    """Read a source PDF: total page count + render one page to image bytes. The PyMuPDF seam,
    injectable so unit tests need neither a real PDF nor the native library."""

    def page_count(self, pdf_path: Path) -> int: ...

    def render(self, pdf_path: Path, page: int, *, dpi: int) -> bytes: ...


class OcrBackend(Protocol):
    """Transcribe one page image to text — the vision-model seam (image→text). Tests inject canned
    page text; the default calls the configured model."""

    def transcribe(self, image_bytes: bytes, prompt: str) -> str: ...


class FitzPageRenderer:
    """Default ``PageRenderer`` — PyMuPDF (``fitz``) page count + JPEG render, verbatim from live
    ``_get_page_count`` / ``_render_page``."""

    def page_count(self, pdf_path: Path) -> int:
        import fitz

        doc = fitz.open(str(pdf_path))
        try:
            return len(doc)
        finally:
            doc.close()

    def render(self, pdf_path: Path, page: int, *, dpi: int) -> bytes:
        import io

        import fitz
        from PIL import Image

        doc = fitz.open(str(pdf_path))
        try:
            pix = doc[page - 1].get_pixmap(dpi=dpi)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        finally:
            doc.close()

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_JPEG_QUALITY)
        return buf.getvalue()


class GeminiOcrBackend:
    """Default ``OcrBackend`` — Gemini vision, verbatim from live ``_ocr_page``. The concrete model
    id comes from ``manifest.ocr.models`` (no baked default); a missing API key is a ``BackendError``."""

    def __init__(self, *, model_id: str, api_key: str | None = None) -> None:
        if not api_key:
            import os

            api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise BackendError("No Gemini API key. Set GEMINI_API_KEY or pass --api-key.")

        from google import genai

        self._client = genai.Client(api_key=api_key)
        self._model_id = model_id

    def transcribe(self, image_bytes: bytes, prompt: str) -> str:
        from google.genai import types

        response = self._client.models.generate_content(
            model=self._model_id,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                        types.Part.from_text(text=prompt),
                    ],
                )
            ],
        )
        return response.text.strip()


# --- pure mechanics ---------------------------------------------------------------------- #

def _render_ocr_prompt(cfg: ResolvedConfig) -> str:
    """Render the book-neutral ``ocr`` template with the book/language context + the blank sentinel."""
    template = PromptTemplate.load("ocr")
    context = build_prompt_context(cfg)
    return template.render(**context, blank_sentinel=SENTINEL_BLANK)


def _ocr_single_page(
    renderer: PageRenderer,
    backend: OcrBackend,
    pdf_path: Path,
    page: int,
    prompt: str,
    progress_dir: Path,
    dpi: int,
) -> int:
    """Render + transcribe one page, persisting the result for resume. Returns ``page``.

    A present progress file short-circuits (resume). A **render** failure is non-transient, so it
    gets no retry — the page becomes an ``[OCR_ERROR: render failed: …]`` sentinel and the run
    continues. A **transcription** failure is retried with ``_RETRY_BACKOFF``, then falls back to an
    ``[OCR_ERROR: …]`` sentinel. Either sentinel lets stitching drop the body without losing the
    page marker. (Extends live ``_ocr_single_page``, which left a render failure unguarded; the
    transcription path is unchanged.)
    """
    page_file = progress_dir / f"page_{page:04d}.json"
    if page_file.exists():
        return page

    try:
        img_bytes = renderer.render(pdf_path, page, dpi=dpi)
    except Exception as exc:  # non-transient → no retry (a corrupt page renders the same each time)
        atomic_write_json(
            page_file,
            {"page": page, "text": f"{SENTINEL_OCR_ERROR_PREFIX}: render failed: {exc}]"},
        )
        return page

    text: str | None = None
    for attempt in range(len(_RETRY_BACKOFF)):
        try:
            text = backend.transcribe(img_bytes, prompt)
            break
        except Exception as exc:  # backend transient failure → retry, then sentinel
            if attempt < len(_RETRY_BACKOFF) - 1:
                if _RETRY_BACKOFF[attempt]:
                    time.sleep(_RETRY_BACKOFF[attempt])
            else:
                text = f"{SENTINEL_OCR_ERROR_PREFIX}: {exc}]"

    atomic_write_json(page_file, {"page": page, "text": text or ""})
    return page


def _process_pages(
    renderer: PageRenderer,
    backend: OcrBackend,
    pdf_path: Path,
    todo: list[int],
    prompt: str,
    progress_dir: Path,
    dpi: int,
    workers: int,
) -> None:
    """Transcribe every ``todo`` page, sequentially or via a thread pool. (Collapses the live
    ``_ocr_pages_sequential`` / ``_ocr_pages_parallel`` pair, whose only difference was a cosmetic
    progress bar, into one behaviour-equivalent loop.)"""
    if workers <= 1:
        for page in todo:
            _ocr_single_page(renderer, backend, pdf_path, page, prompt, progress_dir, dpi)
            if _PAGE_DELAY:
                time.sleep(_PAGE_DELAY)
        return

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                _ocr_single_page, renderer, backend, pdf_path, p, prompt, progress_dir, dpi
            ): p
            for p in todo
        }
        for future in as_completed(futures):
            page = futures[future]
            try:
                future.result()
            except Exception as exc:  # noqa: BLE001 — surface, keep going with other pages
                print(f"    Error on page {page}: {exc}")


def _stitch_pages(
    progress_dir: Path, start: int, end: int
) -> tuple[str, list[dict]]:
    """Stitch per-page JSON files into ``copy3`` text + a page map. Pure given the progress files.

    Each page contributes a ``⟨PAGE:N⟩`` marker line; a ``[BLANK]`` or ``[OCR_ERROR…]`` page
    contributes the marker but no body. ``char_start``/``char_end`` bound the page's body within
    the stitched text. Verbatim from live ``_stitch_pages`` minus the I/O (the caller writes)."""
    parts: list[str] = []
    page_map: list[dict] = []
    pos = 0

    for page in range(start, end + 1):
        page_data = read_json(progress_dir / f"page_{page:04d}.json")
        text = page_data["text"]

        marker = PAGE_MARKER_TEMPLATE.format(page) + "\n"
        parts.append(marker)
        pos += len(marker)

        char_start = pos
        if text and text != SENTINEL_BLANK and not text.startswith(SENTINEL_OCR_ERROR_PREFIX):
            parts.append(text + "\n")
            pos += len(text) + 1

        parts.append("\n")
        pos += 1

        page_map.append({"page": page, "char_start": char_start, "char_end": pos - 1})

    return "".join(parts), page_map


# --- orchestration ----------------------------------------------------------------------- #

def run(
    *,
    workspace: BookWorkspace,
    cfg: ResolvedConfig,
    lang: LanguagePlugin,
    model: str = "pro",
    pages: tuple[int, int] | None = None,
    workers: int = 1,
    api_key: str | None = None,
    renderer: PageRenderer | None = None,
    backend: OcrBackend | None = None,
) -> dict:
    """OCR the source scan in ``workspace`` → ``copy3`` text + page map in ``ws.data``.

    ``model`` selects a role in ``manifest.ocr.models`` (``"pro"`` → ``copy3_raw.txt``, ``"flash"``
    → ``copy3_flash.txt``). ``pages`` is an inclusive 1-indexed range (default: the whole PDF).
    ``renderer``/``backend`` default to the real PyMuPDF/Gemini backends and are injectable so unit
    tests run offline. ``lang`` is unused (OCR is language-neutral) but kept for the uniform
    signature. Returns a summary dict.
    """
    ws = workspace
    ws.ensure()

    if model not in cfg.manifest.ocr.models:
        raise ValueError(
            f"unknown ocr model role {model!r}; manifest declares "
            f"{sorted(cfg.manifest.ocr.models)}"
        )
    if model not in _OUTPUT_NAMES:
        raise ValueError(f"ocr model role {model!r} has no output-filename mapping")

    pdf_path = ws.scans / cfg.manifest.scan.pdf

    using_default_renderer = renderer is None
    renderer = renderer or FitzPageRenderer()
    # The real PyMuPDF renderer needs the PDF on disk; an injected renderer (tests) does not, so
    # the path is merely *resolved* there (D7). A real run with a missing scan is a clean error.
    if using_default_renderer and not pdf_path.is_file():
        raise MissingInputError(f"source scan PDF not found: {pdf_path}")

    if backend is None:
        backend = GeminiOcrBackend(model_id=cfg.manifest.ocr.models[model], api_key=api_key)

    prompt = _render_ocr_prompt(cfg)

    try:
        total_pages = renderer.page_count(pdf_path)
    except Exception as exc:  # a present-but-unreadable PDF is a whole-document backend failure
        raise BackendError(f"could not read the source scan PDF {pdf_path}: {exc}") from exc
    start, end = 1, total_pages
    if pages:
        start, end = pages
        end = min(end, total_pages)
    page_count = end - start + 1

    progress_dir = ws.resolve("state", f"ocr_{model}_pages")
    progress_dir.mkdir(parents=True, exist_ok=True)

    completed = {int(f.stem.split("_")[1]) for f in progress_dir.glob("page_*.json")}
    todo = [p for p in range(start, end + 1) if p not in completed]
    if completed:
        print(f"  OCR [{model}]: resuming — {len(completed)} done, {len(todo)} remaining")
    else:
        print(f"  OCR [{model}]: {page_count} pages "
              f"({cfg.manifest.ocr.models[model]})"
              + (f", {workers} workers" if workers > 1 else ""))

    if todo:
        _process_pages(
            renderer, backend, pdf_path, todo, prompt, progress_dir, _DEFAULT_DPI, workers
        )

    full_text, page_map = _stitch_pages(progress_dir, start, end)

    output_path = ws.resolve("data", _OUTPUT_NAMES[model])
    page_map_path = ws.resolve("data", f"copy3_{model}_page_map.json")
    atomic_write_text(output_path, full_text)
    atomic_write_json(page_map_path, page_map)
    print(f"  OCR text: {output_path.name} ({len(full_text):,} chars); "
          f"page map: {page_map_path.name} ({len(page_map)} pages)")

    return {
        "model": model,
        "pages": page_count,
        "chars": len(full_text),
        "output": str(output_path),
        "page_map": str(page_map_path),
    }
