"""S1.3a — raw addressed capture, the model-level floor (ENGINE_STRUCTURE_PLAN §2-A/§3.0/§11.1; D25).

Synthetic, in-memory witnesses exercise the three neutral primitives of ``structure.capture`` and the
S1.3a done-when properties: a witness segments into a stream of raw atoms that *tile* the source with
furniture captured-with-role (not dropped); a canonical projection built from two witnesses gives
**every canonical atom ≥1 witness derivation**. The real-PLL-bytes floor is ``test_raw_capture_real_input``.

Red-first (PLAN §9): the tiling floor (:func:`assert_capture_tiles`) is exercised positive **and** by
three tampered negatives that share it as a chokepoint (overlap / out-of-bounds / silent loss), so a
weakened check reds at least one. The capture/round-trip coupling is pinned by reconstructing each
atom through the S1.2 floor — drop the hash and a wrong slice would pass capture but red the round-trip.
The canonical-derivation property is asserted over *every* aligned shape (match / primary-only /
secondary-only), so an alignment branch that dropped a derivation reds the headline.
"""

from __future__ import annotations

import pytest

import engine.structure as structure
from engine.errors import CaptureError
from engine.structure import (
    PAGE_UNMAPPED,
    PROCESSING_SCOPE_EXCLUDED,
    PROCESSING_SCOPE_INCLUDED,
    Atom,
    Geom,
    align_streams,
    assert_capture_tiles,
    build_canonical,
    capture_witness,
    duplicate_atom_ids,
    hash_raw,
    reconstruct_raw,
    verify_atom_roundtrip,
)

# A small source with two body paragraphs (the first multi-line), a furniture marker line, and a
# trailing paragraph — blank-line delimited, with the marker glued to nothing so the role split is
# visible. ``[[MARK:N]]`` stands in for any source-noise marker grammar; it is supplied by the test's
# classifier, never known to core (the copy3 ⟨PAGE:N⟩ grammar lives only in the real-input test).
SOURCE = (
    "Nel mezzo del cammin\n"      # body para 1, line 1
    "di nostra vita.\n"           # body para 1, line 2
    "\n"
    "[[MARK:7]]\n"                # furniture line
    "\n"
    "Mi ritrovai per una selva.\n"  # body para 2
)


def _marker_class(line: str) -> str | None:
    """Classify the synthetic marker line as furniture; everything else is body."""
    return "page-furniture" if line.strip().startswith("[[MARK:") else None


def _page_of(start: int, _end: int) -> tuple[int, int]:
    """A toy page map: marker announces its own page; body before it is page 1, after it page 7."""
    if SOURCE[start:].startswith("[[MARK:7]]"):
        return (7, 7)
    return (1, 1) if start < SOURCE.index("[[MARK") else (7, 7)


# --- capture_witness: tiling + roles + the round-trip coupling ----------------------------- #

def test_capture_witness_tiles_source_and_round_trips_every_atom():
    atoms = capture_witness(SOURCE, "copy3", classify_line=_marker_class, page_of=_page_of)
    # tiles with no silent loss (the capture-completeness floor)
    assert_capture_tiles(atoms, SOURCE)
    # every atom's stored text IS the verbatim slice and survives the S1.2 raw round-trip
    for a in atoms:
        assert a.text == SOURCE[a.raw_span[0]:a.raw_span[1]]
        assert a.norm_layer == "raw"
        assert verify_atom_roundtrip(a, SOURCE) == a.text
    # ids unique + witness-tagged
    assert duplicate_atom_ids(atoms) == []
    assert all(a.witness == "copy3" for a in atoms)


def test_capture_witness_preserves_multiline_paragraph_verbatim():
    # The first body paragraph is two physical lines: its single atom's text keeps the internal
    # newline verbatim (no rejoin/collapse — that would break the byte-exact floor, D30).
    atoms = capture_witness(SOURCE, "copy3", classify_line=_marker_class, page_of=_page_of)
    first_body = next(a for a in atoms if a.processing_scope == PROCESSING_SCOPE_INCLUDED)
    assert first_body.text == "Nel mezzo del cammin\ndi nostra vita."
    assert "\n" in first_body.text


def test_furniture_is_captured_with_role_not_dropped():
    atoms = capture_witness(SOURCE, "copy3", classify_line=_marker_class, page_of=_page_of)
    furniture = [a for a in atoms if a.processing_scope == PROCESSING_SCOPE_EXCLUDED]
    assert len(furniture) == 1
    mark = furniture[0]
    assert mark.text == "[[MARK:7]]"                       # captured verbatim...
    assert mark.capture_provenance_class == "page-furniture"  # ...with a role...
    assert mark.page_range == (7, 7)                       # ...and a page
    # captured-but-excluded ≠ never-captured: the marker bytes are inside an atom span, so dropping
    # furniture atoms from the stream would open a non-whitespace gap the tiling floor rejects.
    body_only = [a for a in atoms if a.processing_scope == PROCESSING_SCOPE_INCLUDED]
    with pytest.raises(CaptureError, match="silent loss"):
        assert_capture_tiles(body_only, SOURCE)


def test_capture_witness_defaults_to_all_body_and_unmapped_pages():
    # A witness with no markers and no page map (PLL copy1/copy2): every line is body, every atom
    # carries the unmapped page sentinel.
    src = "alpha line\n\nbeta line\n"
    atoms = capture_witness(src, "copy1")
    assert [a.capture_provenance_class for a in atoms] == ["authorial", "authorial"]
    assert all(a.processing_scope == PROCESSING_SCOPE_INCLUDED for a in atoms)
    assert all(a.page_range == PAGE_UNMAPPED for a in atoms)
    assert_capture_tiles(atoms, src)


# --- assert_capture_tiles: the floor, positive + three tampered negatives ------------------ #

def _atom(source: str, start: int, end: int, atom_id: str) -> Atom:
    slice_ = source[start:end]
    return Atom(
        atom_id=atom_id, text=slice_, raw_span=(start, end), raw_source_hash=hash_raw(slice_),
        page_range=PAGE_UNMAPPED, norm_layer="raw", geom=Geom.absent(),
        capture_provenance_class="authorial",
    )


def test_tiles_raises_on_overlapping_spans():
    src = "0123456789"
    a = [_atom(src, 0, 6, "a0"), _atom(src, 4, 10, "a1")]   # a1 starts before a0 ends
    with pytest.raises(CaptureError, match="overlaps or precedes"):
        assert_capture_tiles(a, src)


def test_tiles_raises_on_out_of_bounds_span():
    src = "short"
    a = [_atom("short and longer", 6, 12, "a0")]            # valid for the long source, not this one
    with pytest.raises(CaptureError, match="out of bounds"):
        assert_capture_tiles(a, src)


def test_tiles_raises_on_silent_loss_of_real_content():
    # A non-whitespace gap between atoms = source bytes captured into no atom. This is the exact
    # failure "everything is brought in" forbids; whitespace gaps are fine, real text is not.
    src = "keep DROPPED keep"
    a = [_atom(src, 0, 4, "a0"), _atom(src, 13, 17, "a1")]   # "DROPPED" (chars 5–11) covered by nothing
    with pytest.raises(CaptureError, match="silent loss"):
        assert_capture_tiles(a, src)


def test_tiles_accepts_whitespace_only_gaps():
    # The positive that makes the silent-loss negative non-vacuous: identical structure but the gap
    # is whitespace, so it passes. (If the check flagged *any* gap, this would red.)
    src = "keep    keep"
    a = [_atom(src, 0, 4, "a0"), _atom(src, 8, 12, "a1")]    # 4-space gap
    assert_capture_tiles(a, src)


# --- align_streams: every opcode shape -------------------------------------------------- #

def _body(texts: list[str], witness: str) -> list[Atom]:
    """Build a witness stream of body atoms from paragraph texts joined by blank lines, so the spans
    are real and the round-trip holds — alignment keys off ``text``."""
    src = "\n\n".join(texts) + "\n"
    return capture_witness(src, witness), src


def test_align_streams_matches_equal_blocks():
    p, _ = _body(["alpha", "beta", "gamma"], "copy1")
    s, _ = _body(["alpha", "beta", "gamma"], "copy2")
    aligned = align_streams(p, s)
    assert len(aligned) == 3
    assert all(pa is not None and sa is not None for pa, sa in aligned)


def test_align_streams_marks_insert_and_delete():
    p, _ = _body(["alpha", "gamma"], "copy1")          # missing "beta"
    s, _ = _body(["alpha", "beta", "gamma"], "copy2")
    aligned = align_streams(p, s)
    # the inserted-in-secondary block aligns to (None, beta)
    inserts = [(pa, sa) for pa, sa in aligned if pa is None and sa is not None]
    assert len(inserts) == 1 and inserts[0][1].text == "beta"


def test_align_streams_normalizes_case_and_whitespace_for_matching():
    # The neutral key folds case + run-length so OCR-variant blocks still align — without an accent
    # or language rule. Same words, different case/spacing → matched, not replaced.
    p, _ = _body(["The  QUICK fox"], "copy1")
    s, _ = _body(["the quick fox"], "copy2")
    aligned = align_streams(p, s)
    assert len(aligned) == 1
    assert aligned[0][0] is not None and aligned[0][1] is not None


# --- build_canonical: the S1.3a done-when property -------------------------------------- #

def test_build_canonical_every_atom_has_at_least_one_derivation():
    # The headline property. Streams that match on some blocks and diverge on others — the canonical
    # must still give EVERY atom a witness back-link (none orphaned).
    p, _ = _body(["shared one", "only in copy1", "shared two"], "copy1")
    s, _ = _body(["shared one", "only in copy2", "shared two"], "copy2")
    canon = build_canonical({"copy1": p, "copy2": s}, ["copy1", "copy2"])
    assert canon, "canonical projection is empty"
    assert all(len(a.derived_from) >= 1 for a in canon)
    assert all(a.witness is None for a in canon)          # canonical is no single witness
    assert duplicate_atom_ids(canon) == []


def test_build_canonical_links_both_witnesses_on_a_matched_block():
    p, _ = _body(["identical block"], "copy1")
    s, _ = _body(["identical block"], "copy2")
    canon = build_canonical({"copy1": p, "copy2": s}, ["copy1", "copy2"])
    assert len(canon) == 1
    witnesses = {d.witness for d in canon[0].derived_from}
    assert witnesses == {"copy1", "copy2"}
    # back-links resolve to the actual per-witness atom ids
    ids = {(d.witness, d.atom_id) for d in canon[0].derived_from}
    assert ("copy1", p[0].atom_id) in ids and ("copy2", s[0].atom_id) in ids


def test_build_canonical_single_witness_block_derives_from_that_witness_only():
    # A block only copy1 has: the canonical atom adopts copy1's text and derives from copy1 alone —
    # still ≥1, the property holds for the asymmetric shape too.
    p, _ = _body(["alpha", "copy1 exclusive", "gamma"], "copy1")
    s, _ = _body(["alpha", "gamma"], "copy2")
    canon = build_canonical({"copy1": p, "copy2": s}, ["copy1", "copy2"])
    solo = [a for a in canon if a.text == "copy1 exclusive"]
    assert len(solo) == 1
    assert [d.witness for d in solo[0].derived_from] == ["copy1"]


def test_build_canonical_secondary_only_block_derives_from_secondary_only():
    # The mirror of the primary-only case and the shape the matched/replace fixtures never produce:
    # a block ONLY copy2 has aligns as (None, s), so the canonical atom adopts copy2's text and its
    # SOLE derivation is copy2. This is the fixture that reds a dropped secondary-derivation branch
    # (a replace/primary-only fixture leaves the primary link in place and hides the bug).
    p, _ = _body(["alpha", "gamma"], "copy1")
    s, _ = _body(["alpha", "copy2 exclusive", "gamma"], "copy2")
    canon = build_canonical({"copy1": p, "copy2": s}, ["copy1", "copy2"])
    solo = [a for a in canon if a.text == "copy2 exclusive"]
    assert len(solo) == 1
    assert [d.witness for d in solo[0].derived_from] == ["copy2"]
    assert all(len(a.derived_from) >= 1 for a in canon)   # ≥1 holds for the secondary-only shape too


def test_canonical_atom_round_trips_against_its_primary_witness_source():
    # A canonical atom's address points into the source of its first derivation's witness. Reconstruct
    # it against that source byte-exact — the floor that keeps the canonical projection addressable.
    p, src1 = _body(["shared", "only copy1"], "copy1")
    s, src2 = _body(["shared", "only copy2"], "copy2")
    sources = {"copy1": src1, "copy2": src2}
    canon = build_canonical({"copy1": p, "copy2": s}, ["copy1", "copy2"])
    for a in canon:
        primary = a.derived_from[0].witness
        assert reconstruct_raw(a, sources[primary]) == a.text


def test_build_canonical_excludes_furniture_from_alignment():
    # Furniture atoms (excluded scope) must not become canonical body atoms — only included atoms
    # align. copy1 here carries a marker; the canonical has no furniture-derived atom.
    src1 = "alpha\n\n[[MARK:1]]\n\nbeta\n"
    p = capture_witness(src1, "copy1", classify_line=_marker_class, page_of=_page_of)
    s, _ = _body(["alpha", "beta"], "copy2")
    canon = build_canonical({"copy1": p, "copy2": s}, ["copy1", "copy2"])
    assert all(a.capture_provenance_class != "page-furniture" for a in canon)
    assert {a.text for a in canon} == {"alpha", "beta"}


def test_build_canonical_requires_two_witnesses():
    p, _ = _body(["alpha"], "copy1")
    with pytest.raises(CaptureError, match="two structural witnesses"):
        build_canonical({"copy1": p}, ["copy1"])


# --- exports ---------------------------------------------------------------------------- #

def test_public_exports_resolve():
    for name in (
        "capture_witness", "build_canonical", "align_streams", "assert_capture_tiles",
        "PAGE_UNMAPPED", "PROCESSING_SCOPE_INCLUDED", "PROCESSING_SCOPE_EXCLUDED",
    ):
        assert name in structure.__all__, f"{name!r} missing from structure.__all__"
        assert hasattr(structure, name), f"{name!r} not importable from engine.structure"
