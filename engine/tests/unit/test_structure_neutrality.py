"""S0.2 — structure-core neutrality guard (ENGINE_STRUCTURE_TASKS).

``engine.structure`` models document structure for *any* book/language. Which word marks a
chapter, which ordinal grammar numbers it, how many parts a book has, which marks quote foreign
terms — all of that is data in the structure profile + the per-book structure map
(ENGINE_STRUCTURE_PLAN §7.1), never code. This guard makes that a standing assertion over
``src/engine/structure/``: a source-language heading word, a guillemet used as a structure marker,
or a baked part/chapter count appearing there is a leak — the F1 (recognition in the language
plugin) / F2 (fixed-shape validator) anti-patterns this axis exists to remove.

Distinct from ``test_core_neutrality`` (book *entities* + typeface, across all of core); this one
targets the structure axis's specific failure mode. Like that guard, the denylist is the
known-leak set, not a completeness proof — semantic leakage (an Italian-only segmentation
assumption with no literal) is caught by profile-extraction review, not this scan. The planted-leak
test below proves the scan is not vacuous (it would catch a real reintroduction).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

STRUCTURE_SRC = Path(__file__).resolve().parents[2] / "src" / "engine" / "structure"
PY_FILES = sorted(STRUCTURE_SRC.rglob("*.py"))

# Language / ordinal / structure literals that must live in the profile or structure map, never in
# the structure core. Three categories the S0.2 done-when names: heading grammar, guillemets, count.
FORBIDDEN = [
    # source-language heading + matter grammar (PLL's, but the rule is general: no source headings)
    "capitolo", "prefazione", "parte prima", "parte seconda",
    # guillemets used as quote/structure markers (the profile declares a book's quote marks)
    "«", "»",
    # PLL's baked structure shape (F2): the live validator's `check_chapter_count` hard-codes the
    # part/chapter count (its `h3_count` result key; the 24+33=57 literals). The general tree model
    # replaces that — either token reappearing in structure/ core is book opinion leaking back in.
    "check_chapter_count", "h3_count",
]


def _hits(term: str, files: list[Path]) -> list[str]:
    """Every ``file:lineno: line`` where ``term`` appears (case-insensitive), the leak report."""
    pat = re.compile(re.escape(term), re.IGNORECASE)
    hits: list[str] = []
    for f in files:
        for lineno, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if pat.search(line):
                hits.append(f"{f.name}:{lineno}: {line.strip()}")
    return hits


def test_structure_src_has_python_files():
    # Guard against a vacuous green: an empty glob would pass every assertion below by scanning
    # nothing (the single-fixture-blind-spot trap).
    assert PY_FILES, f"no .py files under {STRUCTURE_SRC}; the neutrality scan would pass vacuously"


@pytest.mark.parametrize("term", FORBIDDEN)
def test_no_language_or_structure_literal_in_structure_core(term):
    hits = _hits(term, PY_FILES)
    assert not hits, (
        f"language/structure literal {term!r} leaked into engine.structure core — move it to the "
        f"structure profile/map:\n" + "\n".join(hits)
    )


@pytest.mark.parametrize("term", FORBIDDEN)
def test_guard_catches_a_planted_literal(tmp_path, term):
    # The non-vacuity proof: plant each forbidden term in a throwaway file and assert the scan flags
    # it. Without this, an over-narrow regex could silently stop catching reintroductions.
    planted = tmp_path / "leak.py"
    planted.write_text(f'HEADING_MARKER = "{term} ..."\n', encoding="utf-8")
    assert _hits(term, [planted]), f"the guard failed to catch a planted {term!r} — scan is vacuous"
