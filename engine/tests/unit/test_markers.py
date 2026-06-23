"""contracts.markers — the single-sourced OCR page-marker grammar.

The grammar literal exists once (``PAGE_MARKER_TEMPLATE``); ``PAGE_MARKER_RE`` is *derived* from
it, so ``ocr``'s emit format and ``reconcile``'s parse regex cannot drift to different literals
(plan F6). These pin the round-trip and that the regex really is derived.
"""

from __future__ import annotations

import re

from engine.contracts.markers import (
    PAGE_MARKER_RE,
    PAGE_MARKER_TEMPLATE,
    SENTINEL_BLANK,
    SENTINEL_OCR_ERROR_PREFIX,
)


def test_page_marker_roundtrip():
    for n in (1, 7, 42, 278, 1000):
        emitted = PAGE_MARKER_TEMPLATE.format(n)
        m = PAGE_MARKER_RE.match(emitted)
        assert m is not None and int(m.group(1)) == n


def test_regex_is_derived_from_the_template_not_a_second_literal():
    expected = re.escape(PAGE_MARKER_TEMPLATE).replace(re.escape("{}"), r"(\d+)")
    assert PAGE_MARKER_RE.pattern == expected
    # and it equals reconcile's original hand-written form (the port preserved the grammar)
    assert PAGE_MARKER_RE.pattern == r"⟨PAGE:(\d+)⟩"


def test_marker_does_not_match_non_marker_lines():
    assert PAGE_MARKER_RE.match("Capitolo Primo") is None
    assert PAGE_MARKER_RE.match("⟨PAGE:⟩") is None        # no digits
    assert PAGE_MARKER_RE.match("testo ⟨PAGE:3⟩") is None  # not anchored at line start


def test_sentinels_are_the_wire_literals():
    # These cross step boundaries (template↔stitcher, ocr↔reconcile-tolerant), so a change is a
    # deliberate, review-visible protocol change — pinned here.
    assert SENTINEL_BLANK == "[BLANK]"
    assert SENTINEL_OCR_ERROR_PREFIX == "[OCR_ERROR"
