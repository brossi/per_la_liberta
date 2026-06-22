"""Workspace containment, proven end-to-end — the forward-fork's core safety property.

``test_workspace`` proves the *guard* (``BookWorkspace.resolve`` rejects ``..``/absolute
escapes). This proves the *step uses it*: a real ``validate`` run writes only inside its
workspace and leaves the live PLL tree (repo-root ``data/``/``output/``/``state/``) untouched
— so the engine can never overwrite the hand-tuned live edition. Snapshotting those trees
before and after a run is the direct evidence that ``run`` has no path to them.

Containment is independent of what spaCy does (it is purely about *where* writes go), so this
injects a no-op NER stub instead of loading the model. That keeps the safety check in the
*fast* suite — run on every invocation, not gated behind ``integration`` — while the real
spaCy path is exercised by the golden and synthetic-book tests.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from engine.config.loader import load_book
from engine.lang.registry import get_language_plugin
from engine.paths import BookWorkspace
from engine.steps import validate

ENGINE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = ENGINE_ROOT.parent
SYNTHETIC_INPUTS = ENGINE_ROOT / "books" / "synthetic" / "inputs"

# The live pipeline's protected output seam (pipeline.py DATA_DIR/OUTPUT_DIR/STATE_DIR).
PROTECTED = ("data", "output", "state")


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
