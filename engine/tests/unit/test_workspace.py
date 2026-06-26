"""``BookWorkspace`` — area derivation and the path-containment guarantee.

The containment assertion is the unit-level guarantee that the engine cannot write into
the live PLL tree: ``resolve`` must reject any ``..`` traversal or absolute part. (The
fuller before/after-hash isolation test arrives in M2, once a real step actually writes.)
"""

from __future__ import annotations

import pytest

from engine.paths import BookWorkspace


def test_areas_are_under_the_book_work_tree(tmp_path):
    ws = BookWorkspace.for_book("demo", tmp_path)
    assert ws.root == (tmp_path / "demo" / "work").resolve()
    assert ws.data == ws.root / "data"
    assert ws.output == ws.root / "output"
    assert ws.state == ws.root / "state"


def test_ensure_creates_the_three_areas(tmp_path):
    ws = BookWorkspace.for_book("demo", tmp_path).ensure()
    assert ws.data.is_dir() and ws.output.is_dir() and ws.state.is_dir()


def test_resolve_returns_paths_inside_the_workspace(tmp_path):
    ws = BookWorkspace.for_book("demo", tmp_path)
    p = ws.resolve("data", "reconciled_chapters.json")
    assert p == ws.data / "reconciled_chapters.json"
    assert p.is_relative_to(ws.root)


def test_resolve_rejects_unknown_area(tmp_path):
    ws = BookWorkspace.for_book("demo", tmp_path)
    with pytest.raises(ValueError, match="unknown workspace area"):
        ws.resolve("nope", "x.json")


@pytest.mark.parametrize("escape", ["../../../etc/passwd", "../../output/x", "a/../../../x"])
def test_resolve_rejects_traversal_escape(tmp_path, escape):
    ws = BookWorkspace.for_book("demo", tmp_path)
    with pytest.raises(ValueError, match="escapes workspace"):
        ws.resolve("data", escape)


def test_resolve_rejects_absolute_part(tmp_path):
    ws = BookWorkspace.for_book("demo", tmp_path)
    with pytest.raises(ValueError, match="must be relative"):
        ws.resolve("data", "/etc/passwd")


# --- resolve_root: the area-less work-root resolver (S0.1 structure artifacts) ---------- #

def test_resolve_root_returns_paths_at_the_work_root(tmp_path):
    ws = BookWorkspace.for_book("demo", tmp_path)
    p = ws.resolve_root("structure_map.json")
    assert p == ws.root / "structure_map.json"
    assert p.parent == ws.root  # at the root, not under data/output/state
    assert p.is_relative_to(ws.root)


@pytest.mark.parametrize("escape", ["../../../etc/passwd", "../sibling", "a/../../x"])
def test_resolve_root_rejects_traversal_escape(tmp_path, escape):
    ws = BookWorkspace.for_book("demo", tmp_path)
    with pytest.raises(ValueError, match="escapes workspace"):
        ws.resolve_root(escape)


def test_resolve_root_rejects_absolute_part(tmp_path):
    ws = BookWorkspace.for_book("demo", tmp_path)
    with pytest.raises(ValueError, match="must be relative"):
        ws.resolve_root("/etc/passwd")
