"""ocr property/contract tier (non-deterministic step → no equivalence golden, F1).

Render + transcribe are injected; these pin the pure mechanics — ``_stitch_pages`` page-map
invariants, the ``[BLANK]``/``[OCR_ERROR]`` sentinel handling and template↔stitcher *sync* (F6),
resume, the faithful prompt render, and the ``ocr`` → ``reconcile`` marker round-trip that closes
the producer/consumer inversion.
"""

from __future__ import annotations

import pytest

from engine.config.loader import load_book
from engine.contracts.markers import (
    PAGE_MARKER_TEMPLATE,
    SENTINEL_BLANK,
    SENTINEL_OCR_ERROR_PREFIX,
)
from engine.lang.registry import get_language_plugin
from engine.paths import BookWorkspace
from engine.steps import ocr, reconcile
from engine.util.jsonio import atomic_write_json, read_json

# The exact live OCR_PROMPT (top-level ocr.py:27-38) — the port must reproduce it byte-for-byte
# for PLL, proving the templating extraction changed *where* the facts live, not the prompt sent.
_LIVE_OCR_PROMPT = (
    "Transcribe all the text on this page exactly as printed. "
    "This is a page from a 1913 Italian book titled 'Per la libertà!' by Cesare Crespi. "
    "Rules:\n"
    "- Output only the text content, no commentary\n"
    "- Preserve line breaks as they appear on the page\n"
    "- Preserve all accented characters (à, è, ì, ò, ù, é)\n"
    "- Preserve punctuation exactly\n"
    "- If the page has a page number, include it on its own line\n"
    "- If the page is blank or has only decorative elements, output [BLANK]\n"
    "- Do not translate — output the Italian text as printed"
)


def _cfg_lang(book="synthetic"):
    cfg = load_book(book)
    return cfg, get_language_plugin(cfg.language_id)


def _write_pages(progress_dir, page_texts):
    progress_dir.mkdir(parents=True, exist_ok=True)
    for n, t in page_texts.items():
        atomic_write_json(progress_dir / f"page_{n:04d}.json", {"page": n, "text": t})


def test_render_ocr_prompt_is_faithful_to_live_for_pll():
    cfg, _ = _cfg_lang("per_la_liberta")
    assert ocr._render_ocr_prompt(cfg) == _LIVE_OCR_PROMPT


def test_stitch_pages_map_invariants(tmp_path):
    pdir = tmp_path / "prog"
    pages = {1: "Prima pagina di prova.", 2: SENTINEL_BLANK, 3: "[OCR_ERROR: kaboom]"}
    _write_pages(pdir, pages)

    full_text, page_map = ocr._stitch_pages(pdir, 1, 3)

    assert [e["page"] for e in page_map] == [1, 2, 3]
    for e in page_map:
        # every page contributes its marker, ahead of its body region
        marker = PAGE_MARKER_TEMPLATE.format(e["page"])
        assert marker in full_text
        assert full_text.index(marker) < e["char_start"]
        # char_start/char_end bound exactly this page's body within the stitched text
        body = full_text[e["char_start"]:e["char_end"]]
        assert e["char_start"] <= e["char_end"]
        if e["page"] == 1:
            assert body.strip() == pages[1]
        else:
            # BLANK / OCR_ERROR pages keep their marker but contribute no body
            assert e["char_start"] == e["char_end"]
            assert body == ""

    # the sentinel bodies never leak into the stitched output
    assert SENTINEL_BLANK not in full_text
    assert "kaboom" not in full_text


def test_blank_sentinel_template_and_stitcher_use_one_constant(tmp_path):
    # F6: the prompt template instructs the model to emit SENTINEL_BLANK, and the stitcher drops a
    # page whose body IS that same constant. Asserting both sides here proves they cannot drift —
    # if the constant changed, the template no longer instructs what the stitcher matches.
    cfg, _ = _cfg_lang()
    assert SENTINEL_BLANK in ocr._render_ocr_prompt(cfg)

    pdir = tmp_path / "prog"
    _write_pages(pdir, {1: SENTINEL_BLANK})
    full_text, page_map = ocr._stitch_pages(pdir, 1, 1)
    assert page_map[0]["char_start"] == page_map[0]["char_end"]  # body dropped
    assert SENTINEL_BLANK not in full_text


def test_failing_backend_yields_ocr_error_sentinel_then_drops_body(tmp_path, monkeypatch, acq):
    monkeypatch.setattr(ocr, "_RETRY_BACKOFF", (0, 0, 0))
    monkeypatch.setattr(ocr, "_PAGE_DELAY", 0)
    cfg, lang = _cfg_lang()
    ws = BookWorkspace.for_book("synthetic", tmp_path).ensure()

    class _Failing:
        def transcribe(self, image_bytes, prompt):
            raise RuntimeError("vision-down")

    ocr.run(
        workspace=ws, cfg=cfg, lang=lang, model="pro", pages=(1, 2),
        renderer=acq.Renderer(2), backend=_Failing(),
    )

    # progress file carries the typed sentinel; stitched copy3 keeps markers, drops error bodies
    pf = read_json(ws.state / "ocr_pro_pages" / "page_0001.json")
    assert pf["text"].startswith(SENTINEL_OCR_ERROR_PREFIX)
    text = (ws.data / "copy3_raw.txt").read_text(encoding="utf-8")
    assert PAGE_MARKER_TEMPLATE.format(1) in text and PAGE_MARKER_TEMPLATE.format(2) in text
    assert "vision-down" not in text


def test_transient_backend_failure_retries_then_recovers(tmp_path, monkeypatch, acq):
    # The retry loop's RECOVERY path (ocr.py:183-194), which the always-failing backend above never
    # reaches: a transient transcribe failure is retried and a later success transcribes the page
    # normally — it does NOT become a permanent OCR_ERROR sentinel. Guards a regression that disables
    # the retry (e.g. range(1)), which would turn every transient blip into a dropped page.
    monkeypatch.setattr(ocr, "_RETRY_BACKOFF", (0, 0, 0))
    monkeypatch.setattr(ocr, "_PAGE_DELAY", 0)
    cfg, lang = _cfg_lang()
    ws = BookWorkspace.for_book("synthetic", tmp_path).ensure()

    class _FlakyOnce:
        def __init__(self):
            self.calls = 0

        def transcribe(self, image_bytes, prompt):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("transient-blip")
            return "recovered page text"

    backend = _FlakyOnce()
    ocr.run(
        workspace=ws, cfg=cfg, lang=lang, model="pro", pages=(1, 1),
        renderer=acq.Renderer(1), backend=backend,
    )

    pf = read_json(ws.state / "ocr_pro_pages" / "page_0001.json")
    assert pf["text"] == "recovered page text"
    assert not pf["text"].startswith(SENTINEL_OCR_ERROR_PREFIX)
    assert backend.calls == 2  # one failure + one successful retry


def test_unreadable_pdf_page_count_failure_is_a_backend_error(tmp_path, acq):
    # A present-but-corrupt PDF (page_count raises) is a whole-document failure → typed BackendError
    # (exit 5), not a raw fitz traceback. Distinct from the missing-PDF MissingInputError (exit 3).
    from engine.errors import BackendError

    cfg, lang = _cfg_lang()
    ws = BookWorkspace.for_book("synthetic", tmp_path).ensure()

    class _UnreadableDoc:
        def page_count(self, pdf_path):
            raise RuntimeError("cannot open broken document")

        def render(self, pdf_path, page, *, dpi):
            raise AssertionError("render must not be reached — page_count failed first")

    with pytest.raises(BackendError) as ei:
        ocr.run(
            workspace=ws, cfg=cfg, lang=lang, model="pro",
            renderer=_UnreadableDoc(), backend=acq.Backend({}),
        )
    assert ei.value.exit_code == 5
    assert "could not read the source scan PDF" in str(ei.value)


def test_per_page_render_failure_becomes_a_sentinel_and_the_run_continues(tmp_path, monkeypatch):
    # A torn leaf (render raises for one page) does not abort the scan: that page becomes a
    # render-failure [OCR_ERROR] sentinel (no retry — non-transient) while the rest transcribe
    # normally, mirroring the transcription-failure policy. Marker kept, failure body dropped.
    monkeypatch.setattr(ocr, "_PAGE_DELAY", 0)
    cfg, lang = _cfg_lang()
    ws = BookWorkspace.for_book("synthetic", tmp_path).ensure()

    renders: list[int] = []

    class _TornLeafRenderer:
        def page_count(self, pdf_path):
            return 2

        def render(self, pdf_path, page, *, dpi):
            renders.append(page)
            if page == 1:
                raise RuntimeError("torn leaf")
            return str(page).encode()

    class _Backend:
        def transcribe(self, image_bytes, prompt):
            return f"page {int(image_bytes.decode())} text"

    ocr.run(
        workspace=ws, cfg=cfg, lang=lang, model="pro", pages=(1, 2),
        renderer=_TornLeafRenderer(), backend=_Backend(),
    )

    pf1 = read_json(ws.state / "ocr_pro_pages" / "page_0001.json")
    assert pf1["text"].startswith(SENTINEL_OCR_ERROR_PREFIX)
    assert "render failed" in pf1["text"]
    assert renders.count(1) == 1, "a render failure is non-transient → not retried"

    text = (ws.data / "copy3_raw.txt").read_text(encoding="utf-8")
    assert PAGE_MARKER_TEMPLATE.format(1) in text and PAGE_MARKER_TEMPLATE.format(2) in text
    assert "torn leaf" not in text          # the failure detail never leaks into copy3
    assert "page 2 text" in text            # the good page transcribed normally


def test_resume_skips_completed_pages(tmp_path, monkeypatch, acq):
    monkeypatch.setattr(ocr, "_PAGE_DELAY", 0)
    cfg, lang = _cfg_lang()
    ws = BookWorkspace.for_book("synthetic", tmp_path).ensure()
    page_texts = acq.split((acq.inputs / "copy3_raw.txt").read_text(encoding="utf-8"))

    # pre-seed page 1 as already OCR'd with a distinctive body
    _write_pages(ws.state / "ocr_pro_pages", {1: "PRESEEDED ONE"})

    rendered: list[int] = []

    class _CountingRenderer:
        def page_count(self, pdf_path):
            return 2

        def render(self, pdf_path, page, *, dpi):
            rendered.append(page)
            return str(page).encode()

    ocr.run(
        workspace=ws, cfg=cfg, lang=lang, model="pro", pages=(1, 2),
        renderer=_CountingRenderer(), backend=acq.Backend(page_texts),
    )

    assert rendered == [2], "page 1 should resume from cache, only page 2 re-rendered"
    text = (ws.data / "copy3_raw.txt").read_text(encoding="utf-8")
    assert "PRESEEDED ONE" in text  # the resumed page's cached body, not a re-OCR


def test_ocr_to_reconcile_marker_roundtrip(tmp_path):
    # The closing contract: a stitched OCR output is parseable by reconcile's marker stripper +
    # page-map consumer — the ⟨PAGE:N⟩ protocol round-trips between the two ported steps.
    pdir = tmp_path / "prog"
    bodies = {1: "Riga uno.\nRiga due.", 2: "Pagina due, testo."}
    _write_pages(pdir, bodies)
    full_text, page_map = ocr._stitch_pages(pdir, 1, 2)

    clean, page_breaks = reconcile._strip_page_markers(full_text)
    assert sorted(page_breaks.values()) == [1, 2]      # both page numbers recovered
    assert "⟨PAGE" not in clean                          # markers stripped
    assert "Riga uno." in clean and "Pagina due, testo." in clean

    # the page map reconcile reads is well-formed (the shape its chapter_pages logic depends on)
    assert [e["page"] for e in page_map] == [1, 2]
    assert all(e["char_start"] <= e["char_end"] for e in page_map)


def test_unknown_model_role_is_rejected(tmp_path, acq):
    cfg, lang = _cfg_lang()
    ws = BookWorkspace.for_book("synthetic", tmp_path).ensure()
    with pytest.raises(ValueError, match="unknown ocr model role"):
        ocr.run(
            workspace=ws, cfg=cfg, lang=lang, model="nonesuch",
            renderer=acq.Renderer(1), backend=acq.Backend({}),
        )


def test_default_gemini_backend_without_key_is_a_backend_error(monkeypatch):
    # The default backend's missing-key failure branch → typed BackendError (exit 5), not a bare
    # ValueError. Exercised without network (construction fails before any client call).
    from engine.errors import BackendError

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(BackendError, match="No Gemini API key"):
        ocr.GeminiOcrBackend(model_id="whatever")


def test_missing_scan_pdf_is_a_clean_error_with_default_renderer(tmp_path):
    # The real renderer needs the PDF on disk; absent → a typed MissingInputError (exit 3), not a
    # PyMuPDF traceback. (Default renderer path; no PDF created, no network — the guard fires
    # before any fitz call.)
    from engine.errors import MissingInputError

    cfg, lang = _cfg_lang()
    ws = BookWorkspace.for_book("synthetic", tmp_path).ensure()
    with pytest.raises(MissingInputError, match="source scan PDF not found"):
        ocr.run(workspace=ws, cfg=cfg, lang=lang, model="pro", pages=(1, 1))


@pytest.mark.integration
def test_fitz_renderer_and_run_against_a_real_pdf(tmp_path, monkeypatch):
    # The lone real-fitz smoke (D7): exercises the PyMuPDF binding (page_count + render → JPEG)
    # AND the full ocr.run path with the *default* renderer on a real 2-page PDF, transcription
    # canned (no network). Validate-bindings: the import + render path runs, not shape-asserted.
    import fitz

    monkeypatch.setattr(ocr, "_PAGE_DELAY", 0)
    cfg, lang = _cfg_lang()

    # The scan PDF resolves to books/<id>/scans/<manifest.scan.pdf> — build a real one there.
    ws = BookWorkspace.for_book("synthetic", tmp_path).ensure()
    ws.scans.mkdir(parents=True, exist_ok=True)
    pdf_path = ws.scans / cfg.manifest.scan.pdf
    doc = fitz.open()
    for i in range(2):
        doc.new_page().insert_text((72, 72), f"Pagina di prova {i + 1}")
    doc.save(str(pdf_path))
    doc.close()

    # Direct binding check: real render returns JPEG bytes (SOI marker), real page_count is 2.
    renderer = ocr.FitzPageRenderer()
    assert renderer.page_count(pdf_path) == 2
    assert renderer.render(pdf_path, 1, dpi=72)[:2] == b"\xff\xd8"

    class _ConstBackend:
        def transcribe(self, image_bytes, prompt):
            assert image_bytes[:2] == b"\xff\xd8"  # received a real rendered JPEG
            return "testo OCR di prova"

    result = ocr.run(
        workspace=ws, cfg=cfg, lang=lang, model="pro", pages=(1, 2),
        backend=_ConstBackend(),  # default (real fitz) renderer
    )
    assert result["pages"] == 2
    text = (ws.data / "copy3_raw.txt").read_text(encoding="utf-8")
    assert PAGE_MARKER_TEMPLATE.format(1) in text and PAGE_MARKER_TEMPLATE.format(2) in text
    assert text.count("testo OCR di prova") == 2
