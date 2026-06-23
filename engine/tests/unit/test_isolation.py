"""Workspace containment, proven end-to-end — the forward-fork's core safety property.

``test_workspace`` proves the *guard* (``BookWorkspace.resolve`` rejects ``..``/absolute
escapes). This proves each *ported step uses it*: a real ``run`` writes only inside its
workspace and leaves every live PLL tree untouched — so the engine can never overwrite the
hand-tuned live edition. Snapshotting those trees before and after a run is the direct evidence
that ``run`` has no path to them. Each ported step earns a function here as it lands (validate
M2, reconcile M3, adjudicate M3).

The protected set is the *five* repo-root trees the engine must never write: the live
pipeline's ``data``/``output``/``state`` seam (``pipeline.py``) **plus** the published-edition
``docs``/``static`` (typeset's live targets, currently deploy-held). Even steps that only write
``ws.data`` are checked against all five — the guarantee is that *no* step can reach *any* live
tree, not merely the one it happens to use.

Containment is independent of what spaCy does (it is purely about *where* writes go), so the
validate case injects a no-op NER stub instead of loading the model, and adjudicate injects a
fake dictionary oracle. That keeps the safety check in the *fast* suite — run on every
invocation, not gated behind ``integration`` — while the real model/dictionary paths are
exercised by the golden and synthetic-book tests.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from engine.config.loader import load_book
from engine.lang.registry import get_language_plugin
from engine.paths import BookWorkspace
from engine.steps import adjudicate, download, ocr, reconcile, validate

ENGINE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = ENGINE_ROOT.parent
SYNTHETIC_INPUTS = ENGINE_ROOT / "books" / "synthetic" / "inputs"

# The five live trees the engine must never write: the pipeline output seam
# (data/output/state) plus the published edition (docs/static, typeset's targets).
PROTECTED = ("data", "output", "state", "docs", "static")


class _StubDoc:
    ents = ()


def _stub_nlp(_text):
    return _StubDoc()


def _snapshot(root: Path) -> dict[str, tuple[int, int]]:
    """Map every file under ``root``'s protected dirs to (size, mtime_ns). Any write,
    overwrite, or delete changes this snapshot."""
    snap: dict[str, tuple[int, int]] = {}
    for area in PROTECTED:
        base = root / area
        if not base.is_dir():
            continue
        for dirpath, _dirs, files in os.walk(base):  # does not follow dir symlinks
            for name in files:
                p = Path(dirpath) / name
                try:
                    st = p.stat()
                except OSError:
                    continue
                snap[str(p.relative_to(root))] = (st.st_size, st.st_mtime_ns)
    return snap


def test_validate_leaves_live_tree_untouched(tmp_path, monkeypatch):
    cfg = load_book("synthetic")
    lang = get_language_plugin(cfg.language_id)
    # Containment doesn't depend on real NER — stub it so this stays a fast, always-run check.
    monkeypatch.setattr(lang, "load_spacy", lambda *a, **k: _stub_nlp)

    ws = BookWorkspace.for_book("synthetic", tmp_path).ensure()
    (ws.output / validate.CLEAN_FILE).write_text(
        (SYNTHETIC_INPUTS / "clean.md").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (ws.data / validate.RECONCILED_FILE).write_text(
        (SYNTHETIC_INPUTS / "reconciled_chapters.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    before = _snapshot(REPO_ROOT)
    report = validate.run(workspace=ws, cfg=cfg, lang=lang)
    after = _snapshot(REPO_ROOT)

    assert before == after, "validate wrote into the live PLL tree"

    # And the report did land — inside the workspace, under tmp_path, not the repo. (The
    # verdict isn't asserted: containment is about *where* the write goes, not the outcome.)
    written = ws.data / validate.REPORT_FILE
    assert written.is_file()
    assert json.loads(written.read_text(encoding="utf-8")) == report
    assert tmp_path in written.parents
    assert REPO_ROOT not in written.parents


_RECONCILE_INPUTS = (
    "copy1_raw.txt", "copy2_raw.txt", "copy3_raw.txt", "copy3_flash_page_map.json",
)


def test_reconcile_leaves_live_tree_untouched(tmp_path):
    # reconcile needs no spaCy/network — it only reads the OCR copies and writes ws.data. The
    # snapshot still covers all five trees: the proof is that it *cannot* reach any of them.
    cfg = load_book("synthetic")
    lang = get_language_plugin(cfg.language_id)
    ws = BookWorkspace.for_book("synthetic", tmp_path).ensure()
    for name in _RECONCILE_INPUTS:
        (ws.data / name).write_text(
            (SYNTHETIC_INPUTS / name).read_text(encoding="utf-8"), encoding="utf-8"
        )

    before = _snapshot(REPO_ROOT)
    reconcile.run(workspace=ws, cfg=cfg, lang=lang)
    after = _snapshot(REPO_ROOT)

    assert before == after, "reconcile wrote into a live PLL tree"

    written = ws.data / reconcile.RECONCILED_FILE
    assert written.is_file()
    assert tmp_path in written.parents
    assert REPO_ROOT not in written.parents


def test_download_leaves_live_tree_untouched(tmp_path, acq):
    # download writes only ws.data via an injected fetcher (no network). The snapshot covers all
    # five live trees: the proof is that it cannot reach any of them.
    cfg = load_book("synthetic")
    lang = get_language_plugin(cfg.language_id)
    ws = BookWorkspace.for_book("synthetic", tmp_path).ensure()
    url_map = {download.source_url(s): f"x-{s.role}" for s in cfg.manifest.sources}

    before = _snapshot(REPO_ROOT)
    download.run(workspace=ws, cfg=cfg, lang=lang, fetcher=acq.Fetcher(url_map))
    after = _snapshot(REPO_ROOT)

    assert before == after, "download wrote into a live PLL tree"
    written = ws.data / "copy1_raw.txt"
    assert written.is_file()
    assert tmp_path in written.parents and REPO_ROOT not in written.parents


def test_ocr_leaves_live_tree_untouched(tmp_path, monkeypatch, acq):
    # ocr with injected render+transcribe (no PDF, no network). Progress lands in ws.state, the
    # witness + page map in ws.data; no live tree is reachable.
    monkeypatch.setattr(ocr, "_PAGE_DELAY", 0)
    cfg = load_book("synthetic")
    lang = get_language_plugin(cfg.language_id)
    ws = BookWorkspace.for_book("synthetic", tmp_path).ensure()
    page_texts = acq.split((acq.inputs / "copy3_raw.txt").read_text(encoding="utf-8"))
    last = max(page_texts)

    before = _snapshot(REPO_ROOT)
    ocr.run(
        workspace=ws, cfg=cfg, lang=lang, model="pro", pages=(1, last),
        renderer=acq.Renderer(last), backend=acq.Backend(page_texts),
    )
    after = _snapshot(REPO_ROOT)

    assert before == after, "ocr wrote into a live PLL tree"
    written = ws.data / "copy3_raw.txt"
    assert written.is_file()
    assert tmp_path in written.parents and REPO_ROOT not in written.parents


class _FakeOracle:
    """A no-knowledge membership oracle — containment is about *where* writes go, not the
    dictionary, so this keeps adjudicate's isolation check fast (no 13 MB asset load)."""

    name = "FakeDict"

    def __call__(self, word):
        return False, []


def test_adjudicate_leaves_live_tree_untouched(tmp_path):
    cfg = load_book("synthetic")
    lang = get_language_plugin(cfg.language_id)
    ws = BookWorkspace.for_book("synthetic", tmp_path).ensure()
    (ws.data / adjudicate.REVIEW_FLAGS_FILE).write_text(
        (SYNTHETIC_INPUTS / "review_flags.json").read_text(encoding="utf-8"), encoding="utf-8"
    )

    before = _snapshot(REPO_ROOT)
    adjudicate.run(workspace=ws, cfg=cfg, lang=lang, oracle=_FakeOracle())
    after = _snapshot(REPO_ROOT)

    assert before == after, "adjudicate wrote into a live PLL tree"

    written = ws.data / adjudicate.RESULTS_FILE
    assert written.is_file()
    assert tmp_path in written.parents
    assert REPO_ROOT not in written.parents
