"""Vision review of the 1913 source-page scans — one home for every operation
that must RE-READ the original pages (divergence-audit re-adjudication,
corrupted-passage repair, future re-OCR). The model choice and the image
handling live here so consumers never re-implement them.

Reader is **Gemini 3.1 Pro** (`gemini-3.1-pro-preview`) — the strongest vision of
the 2026-06 frontier crop on these scans. For a ground-truth scan re-read the
right escalation signal is NOT a second model (a weaker reader than the best
one buys nothing, and Anthropic in particular rejects >5 MB images and downsizes
anything past ~1568 px — below the resolution the Bodoni face needs); it is the
**second physical copy**, read by the same best eyes. `read_*` still accepts any
model name (`_read_claude` is kept for future crop-sized cross-checks), but the
divergence reviewer reads both copies with Gemini.

Two independent physical copies back the scans, and they don't share damage:
- **Copy A — LoC** (`docs/assets/page_images/page_NNNN.png`): one book page per
  file; scan page = printed folio + `LOC_FOLIO_OFFSET` (constant in the body).
- **Copy B — Harvard/Google** (rendered on demand from the PDF): an independent
  printing of the same 1913 edition, ~2–3 pages ahead of LoC (its front matter
  has fewer leaves, with a one-page step partway). `harvard_window()` returns the
  small page window that covers a LoC site. Copy B is the escalation second
  witness: where the LoC scan is foxed/faint, the other copy usually is not.

Resolution is not a detail: the 1913 Bodoni/Didone face confuses c/e and i/r
when shrunk — a downsampled full page reads "cielo" as "eielo", yet the same
model at NATIVE resolution reads it correctly (smoke-tested 2026-06). So pages
go to the model at native size, JPEG q90 (~2 MB, under the 5 MB request ceiling).
Never downsample a page you intend to transcribe.
"""

import base64
import io
import json
import os
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).parent
PAGE_DIR = ROOT / "docs" / "assets" / "page_images"          # Copy A — LoC
HARVARD_PDF = ROOT / "harvard_perlalibertdall00cresgoog.pdf"  # Copy B — Harvard/Google
HARVARD_DIR = ROOT / "assets" / "page_images_harvard"         # rendered on demand (gitignored)

PRIMARY = "gemini-3.1-pro-preview"   # best vision of the current crop (2026-06)
JPEG_QUALITY = 90                    # native res + q90 reads correctly

# LoC scan page = printed folio + this (verified at folios 44/94/194). Harvard
# runs ~2–3 pages ahead of LoC in the body (one-page step partway), so a [+2,+3]
# window over the LoC page covers the matching Harvard page — see harvard_window().
LOC_FOLIO_OFFSET = 6


def _jpeg(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.convert("RGB").save(buf, format="JPEG", quality=JPEG_QUALITY)
    return buf.getvalue()


def page_jpeg(pg: int) -> bytes:
    """Copy A (LoC) page as native-resolution JPEG. NEVER downsample (module note)."""
    return _jpeg(Image.open(PAGE_DIR / f"page_{pg:04d}.png"))


def harvard_jpeg(scan_pg: int) -> bytes:
    """Copy B (Harvard) scan page (1-based), rendered from the PDF and cached as PNG."""
    png = HARVARD_DIR / f"page_{scan_pg:04d}.png"
    if not png.exists():
        import fitz

        HARVARD_DIR.mkdir(parents=True, exist_ok=True)
        doc = fitz.open(HARVARD_PDF)
        pix = fitz.Pixmap(doc, doc[scan_pg - 1].get_images(full=True)[0][0])
        Image.frombytes("L", (pix.width, pix.height), pix.samples).save(png)
    return _jpeg(Image.open(png))


CONCORDANCE = ROOT / "data" / "page_concordance.json"
_concordance_cache: dict | None = None


def _concordance() -> dict:
    """The human-validated LoC->Harvard page map (build_concordance.py). Replaces the
    old fixed +2/+3 offset, which was wrong for ~1/3 of pages (variable offset) and
    blind to Harvard's resolution striping."""
    global _concordance_cache
    if _concordance_cache is None:
        _concordance_cache = (json.loads(CONCORDANCE.read_text(encoding="utf-8"))["map"]
                              if CONCORDANCE.exists() else {})
    return _concordance_cache


def harvard_page(loc_page: int) -> int | None:
    """Exact Harvard PDF page for a LoC page, or None (e.g. folio 131, a skipped leaf)."""
    row = _concordance().get(str(loc_page))
    return row.get("harvard_page") if row else None


def harvard_res(loc_page: int) -> str | None:
    """'full' or 'low' — whether Copy B can settle fine glyphs on this page or only corroborate."""
    row = _concordance().get(str(loc_page))
    return row.get("harvard_res") if row else None


def harvard_window(loc_pages) -> list[int]:
    """Harvard scan pages holding the same text as the given LoC pages, via the verified
    concordance. Pages with no Harvard counterpart contribute nothing (no false page)."""
    return sorted({hp for l in loc_pages if (hp := harvard_page(l)) is not None})


# --- readers: take labeled images so a caller can mix Copy A and Copy B ---

def _read_gemini(images: list[tuple[str, bytes]], system: str, user: str, model: str,
                 json_out: bool = True, thinking: str | None = None) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    parts: list = []
    for label, data in images:
        parts.append(types.Part.from_text(text=f"[{label}]"))
        parts.append(types.Part.from_bytes(data=data, mime_type="image/jpeg"))
    parts.append(types.Part.from_text(text=user))
    # Pinning JSON output truncates long verbatim transcription (it stops after one
    # column / emits a stray array). For a full-page read pass json_out=False.
    cfg = dict(system_instruction=system, max_output_tokens=8000)
    if json_out:
        cfg["response_mime_type"] = "application/json"
    # thinking_level (low|medium|high) trades reasoning budget for cost. Transcription
    # is insensitive to it (verified on a dense page), but hard glyph-adjudication on a
    # small set benefits — so callers pick per regime; omit for the model default.
    if thinking:
        cfg["thinking_config"] = types.ThinkingConfig(thinking_level=thinking)
    resp = client.models.generate_content(
        model=model,
        contents=types.Content(role="user", parts=parts),
        config=types.GenerateContentConfig(**cfg),
    )
    return resp.text or ""


def _read_claude(images: list[tuple[str, bytes]], system: str, user: str, model: str) -> str:
    import anthropic

    c = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=600)
    content: list[dict] = []
    for label, data in images:
        content.append({"type": "text", "text": f"[{label}]"})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                    "data": base64.standard_b64encode(data).decode()}})
    content.append({"type": "text", "text": user})
    r = c.messages.create(model=model, max_tokens=8000, system=system,
                          messages=[{"role": "user", "content": content}])
    return "".join(b.text for b in r.content if b.type == "text")


def read_images(images: list[tuple[str, bytes]], system: str, user: str, model: str = PRIMARY,
                json_out: bool = True, thinking: str | None = None) -> str:
    """Raw model text for a vision question over labeled (label, jpeg_bytes) images.

    With json_out (default) Gemini is pinned to JSON; the user prompt must still ask
    for JSON for Claude, which only obeys the instruction. Pass json_out=False for a
    long plain-text transcription (JSON pinning truncates those — see _read_gemini).
    `thinking` (Gemini only) sets the thinking_level; None uses the model default.
    """
    if model.startswith("gemini"):
        return _read_gemini(images, system, user, model, json_out=json_out, thinking=thinking)
    return _read_claude(images, system, user, model)


def read_pages(pages, system: str, user: str, model: str = PRIMARY, json_out: bool = True) -> str:
    """Convenience: read a question over LoC (Copy A) page scans by page number."""
    images = [(f"Copy A (LoC) scan p.{p}", page_jpeg(p)) for p in sorted(set(pages))]
    return read_images(images, system, user, model, json_out=json_out)


def _strip_fences(raw: str) -> str:
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    return s.strip()


def _parse(raw: str):
    try:
        return json.loads(_strip_fences(raw))
    except (json.JSONDecodeError, ValueError):
        return None


def read_json(pages, system: str, user: str, model: str = PRIMARY):
    """`read_pages` + tolerant JSON parse. Returns (parsed, raw); parsed is None on
    a non-JSON response — treat that as a failed read (retry/escalate), not empty."""
    raw = read_pages(pages, system, user, model)
    return _parse(raw), raw


def read_json_images(images, system: str, user: str, model: str = PRIMARY, thinking: str | None = None):
    """`read_images` + tolerant JSON parse. Returns (parsed, raw)."""
    raw = read_images(images, system, user, model, thinking=thinking)
    return _parse(raw), raw
