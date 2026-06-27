"""S1.3a — raw addressed capture on REAL PLL bytes (ENGINE_STRUCTURE_PLAN §2-A/§3.0/§11.1; D25, F4).

The model floor (``test_raw_capture``) runs on synthetic text. This is the real-input slice: it runs
``structure.capture`` against the *committed* PLL witnesses (``books/per_la_liberta/inputs/copy{1,2,3}_raw.txt``)
and copy3's page map, with the PLL ``⟨PAGE:N⟩`` page-marker grammar supplied **here**, never in core —
the copy3 source-noise convention lives in this per-book binding (the S0.2 neutrality guard scans
``structure/``, not this test).

What real bytes verify that synthetic cannot:

1. **Capture completeness on the whole witness** — copy3 segments into body paragraphs + page-marker
   furniture that **tile the witness with zero silent loss**: every one of ~790K codepoints is inside
   an atom span or inter-atom whitespace. The furniture count is bound to an *independent* regex over
   the witness (two computations of "how many markers" must agree), so a segmenter that swallowed a
   marker into a body atom reds. This is the capture-completeness invariant S1.4 promotes to a gate.
2. **Page attribution at scale** — copy3 is the only page-addressable witness: every body atom lands
   on a real page and each ``⟨PAGE:N⟩`` furniture atom carries ``(N, N)``; copy1/copy2 (0 form-feeds,
   no map) carry :data:`~engine.structure.PAGE_UNMAPPED` throughout.
3. **The canonical projection over real divergence** — aligning the full copy1/copy2 streams (~3.6K vs
   ~3.4K paragraphs of independently-OCR'd text) yields a canonical stream where **every atom has ≥1
   witness derivation** (the S1.3a done-when), ~46% link both witnesses, ids are unique, and each atom
   round-trips byte-exact against its primary witness's source.

Tiers (each proven red, PLAN §9): completeness (``assert_capture_tiles`` over the real witness) +
negatives (a tampered overlap / silent loss on real bytes share that chokepoint). Frozen counts are
derived from the committed fixtures; **refresh them if the witnesses/page map are regenerated.**
"""

from __future__ import annotations

import json
import re
from bisect import bisect_right
from pathlib import Path

import pytest

from engine.errors import CaptureError
from engine.structure import (
    PAGE_UNMAPPED,
    PROCESSING_SCOPE_EXCLUDED,
    PROCESSING_SCOPE_INCLUDED,
    assert_capture_tiles,
    build_canonical,
    capture_witness,
    duplicate_atom_ids,
    reconstruct_raw,
)

INPUTS = Path(__file__).resolve().parents[2] / "books" / "per_la_liberta" / "inputs"
COPY1 = INPUTS / "copy1_raw.txt"
COPY2 = INPUTS / "copy2_raw.txt"
COPY3 = INPUTS / "copy3_raw.txt"
PAGE_MAP = INPUTS / "copy3_pro_page_map.json"

PAGE_MARKER = re.compile(r"⟨PAGE:(\d+)⟩")

# Frozen counts, derived from the committed fixtures (segmentation of the witness bytes). A change to
# the witnesses, the page map, or capture_witness's segmentation reds the bound assertion.
FROZEN_COPY3_FURNITURE = 278       # == independent regex marker count (the binding oracle)
FROZEN_COPY3_BODY = 521
FROZEN_COPY1_ATOMS = 3621
FROZEN_COPY2_ATOMS = 3356


def _read(path: Path) -> str:
    # Hard, not skipped (matches test_roundtrip_real_input / test_sidecar_contracts): these are
    # committed required fixtures; a skipif would turn the whole real-input floor silently green.
    assert path.is_file(), f"frozen PLL witness missing: {path}"
    text = path.read_text(encoding="utf-8")
    assert text, f"witness {path.name} is empty — capture would tile vacuously"
    return text


def _pll_copy3_binding(text: str):
    """The PLL copy3 per-book binding: a ``classify_line`` that tags ``⟨PAGE:N⟩`` lines as
    page-furniture, and a ``page_of`` that reads copy3's page map (and parses a marker's own page).
    This grammar is source-noise — it lives here, never in ``structure/`` core."""
    assert PAGE_MAP.is_file(), f"frozen PLL page map missing: {PAGE_MAP}"
    page_map = json.loads(PAGE_MAP.read_text(encoding="utf-8"))
    assert page_map, "copy3 page map is empty"
    starts = [p["char_start"] for p in page_map]

    def page_at(off: int) -> int | None:
        i = bisect_right(starts, off) - 1
        if 0 <= i < len(page_map) and page_map[i]["char_start"] <= off < page_map[i]["char_end"]:
            return page_map[i]["page"]
        return None

    def classify_line(line: str) -> str | None:
        return "page-furniture" if PAGE_MARKER.fullmatch(line.strip()) else None

    def page_of(start: int, end: int) -> tuple[int, int]:
        m = PAGE_MARKER.fullmatch(text[start:end].strip())
        if m:
            return (int(m.group(1)), int(m.group(1)))
        a, b = page_at(start), page_at(max(start, end - 1))
        return (a if a is not None else -1, b if b is not None else -1)

    return classify_line, page_of


# --- capture completeness on the real witness ------------------------------------------- #

def test_copy3_segments_and_tiles_with_zero_silent_loss():
    text = _read(COPY3)
    classify_line, page_of = _pll_copy3_binding(text)
    atoms = capture_witness(text, "copy3", classify_line=classify_line, page_of=page_of)
    # the capture-completeness floor on ~790K real codepoints: nothing captured into no atom
    assert_capture_tiles(atoms, text)
    assert duplicate_atom_ids(atoms) == []
    body = [a for a in atoms if a.processing_scope == PROCESSING_SCOPE_INCLUDED]
    furniture = [a for a in atoms if a.processing_scope == PROCESSING_SCOPE_EXCLUDED]
    assert len(body) == FROZEN_COPY3_BODY
    assert len(furniture) == FROZEN_COPY3_FURNITURE


def test_copy3_furniture_count_binds_to_an_independent_marker_oracle():
    text = _read(COPY3)
    classify_line, page_of = _pll_copy3_binding(text)
    atoms = capture_witness(text, "copy3", classify_line=classify_line, page_of=page_of)
    furniture = [a for a in atoms if a.capture_provenance_class == "page-furniture"]
    # the binding: the number of furniture atoms equals an independent regex count of the marker —
    # a segmenter that welded a marker into a body block (the probe's exact risk) would disagree.
    assert len(furniture) == len(PAGE_MARKER.findall(text)) == FROZEN_COPY3_FURNITURE
    # every furniture atom is an excluded, verbatim marker that round-trips
    for a in furniture:
        assert PAGE_MARKER.fullmatch(a.text)
        assert a.processing_scope == PROCESSING_SCOPE_EXCLUDED
        assert reconstruct_raw(a, text) == a.text


def test_copy3_pages_attributed_body_real_furniture_self():
    text = _read(COPY3)
    classify_line, page_of = _pll_copy3_binding(text)
    atoms = capture_witness(text, "copy3", classify_line=classify_line, page_of=page_of)
    body = [a for a in atoms if a.processing_scope == PROCESSING_SCOPE_INCLUDED]
    # every body atom lands on a real page (copy3 is the page-addressable witness)
    assert all(a.page_range != PAGE_UNMAPPED for a in body)
    assert all(a.page_range[0] >= 1 and a.page_range[1] >= a.page_range[0] for a in body)
    # each ⟨PAGE:N⟩ furniture atom carries the page it announces
    for a in atoms:
        if a.capture_provenance_class == "page-furniture":
            n = int(PAGE_MARKER.fullmatch(a.text).group(1))
            assert a.page_range == (n, n)


def test_copy1_copy2_tile_and_are_page_unmapped():
    for path, witness, frozen in ((COPY1, "copy1", FROZEN_COPY1_ATOMS),
                                  (COPY2, "copy2", FROZEN_COPY2_ATOMS)):
        text = _read(path)
        atoms = capture_witness(text, witness)   # no markers, no page map → all-body, unmapped
        assert_capture_tiles(atoms, text)
        assert len(atoms) == frozen
        assert all(a.page_range == PAGE_UNMAPPED for a in atoms)
        assert all(a.processing_scope == PROCESSING_SCOPE_INCLUDED for a in atoms)
        assert duplicate_atom_ids(atoms) == []


# --- the negatives: real bytes, sharing the assert_capture_tiles chokepoint -------------- #

def test_real_overlap_fails_capture_tiles():
    text = _read(COPY1)
    atoms = capture_witness(text, "copy1")
    import dataclasses
    bad = list(atoms)
    # widen one atom's span to swallow into the next — an overlap on real offsets
    s, _e = bad[5].raw_span
    bad[5] = dataclasses.replace(bad[5], raw_span=(s, bad[7].raw_span[0] + 1))
    with pytest.raises(CaptureError, match="overlaps or precedes"):
        assert_capture_tiles(bad, text)


def test_real_dropped_atom_is_silent_loss():
    text = _read(COPY1)
    atoms = capture_witness(text, "copy1")
    # remove a body atom: its real-text bytes are now captured into nothing → silent loss
    bad = atoms[:10] + atoms[11:]
    with pytest.raises(CaptureError, match="silent loss"):
        assert_capture_tiles(bad, text)


# --- the canonical projection over real copy1/copy2 divergence --------------------------- #

def test_real_canonical_every_atom_derived_and_round_trips():
    t1, t2 = _read(COPY1), _read(COPY2)
    a1 = capture_witness(t1, "copy1")
    a2 = capture_witness(t2, "copy2")
    canon = build_canonical({"copy1": a1, "copy2": a2}, ["copy1", "copy2"])
    assert canon, "canonical projection is empty"
    # the S1.3a done-when, on real divergent OCR streams: no canonical atom is orphaned
    assert all(len(a.derived_from) >= 1 for a in canon)
    assert all(a.witness is None for a in canon)
    assert duplicate_atom_ids(canon) == []
    # a meaningful fraction reconcile both witnesses (not a degenerate copy1-only projection)
    both = sum(1 for a in canon if len(a.derived_from) == 2)
    assert both > len(canon) // 4, f"only {both}/{len(canon)} canonical atoms link both witnesses"
    # every canonical atom round-trips byte-exact against the source of its primary derivation
    sources = {"copy1": t1, "copy2": t2}
    for a in canon:
        assert reconstruct_raw(a, sources[a.derived_from[0].witness]) == a.text
