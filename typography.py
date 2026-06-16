"""Restore the 1913 printing's typographic conventions, lost during OCR.

OCR captures characters, not type style, so every italic, small-cap, and set-off
verse line in the source printing was flattened to ordinary roman prose. This
module re-applies those conventions from a hand-curated, scan-verified sidecar
(``data/typography.json``) at a single point: ``typeset.py``, on each parsed
paragraph, just before markdown->HTML conversion.

The sidecar is the sole semantic source of truth for typography. It feeds the
web edition (markers below -> HTML in ``_para_to_html``) and is the natural
input for the future InDesign print export (each ``style`` -> a named character
or paragraph style). The ``.md`` files stay clean text — no styling markup is
written back into them, so ``validate.py`` (which reads ``italian_clean.md``) is
unaffected.

Sidecar shape — keyed by the slug chapter id that ``typeset.py`` uses (the
``parse_italian_markdown`` scheme: ``prefazione``, ``p1_capitolo_primo`` ..
``p2_capitolo_trentesimo_terzo``), one entry per emphasized span::

    {
      "prefazione": [
        {
          "style": "verse",
          "it": "\"Giudica e manda secondo che avvinghia\"",
          "en": "“Judges and consigns according to how he coils”",
          "note": "Dante, Inferno V.6 — centered italic display line, p.7"
        }
      ]
    }

Each entry carries the verbatim text to mark per language (``it`` / ``en``); a
language key may be omitted when only one edition uses the convention for that
span.

Disambiguation when a word recurs in a chapter (there is no stable paragraph
id to address by position):

- ``<lang>_anchor`` — a longer verbatim context containing the fragment (e.g.
  ``"it_anchor": "un uomo noto al Popolo ed ai suoi tiranni"``). The fragment is
  wrapped only inside the first instance of that anchor, so "the Popolo in *this*
  sentence" is addressable. Two same-word entries get distinct anchors.
- ``occurrences`` — ``"first"`` (default), ``"all"`` (a word emphasized
  throughout), or a 1-based int. Applies within the anchor region when one is
  given, else across the whole paragraph.

``style`` is one of:

- ``italic``     — inline emphasis -> ``<em>`` (scan-restored; kept distinct from
                   the translator's markdown ``*...*``, which become ``<em
                   class="translator">``)
- ``bold``       — inline heavy emphasis (the 1913 printer's bold concept-words,
                   e.g. Mazzini's "Popolo") -> ``<strong>``
- ``small-caps`` — inline small capitals -> ``<span class="sc">``
- ``all-caps``   — full capitals the 1913 printer used for emphasis on otherwise
                   ordinary words (e.g. "Sì"/"No" set as SI/NO) -> ``<span
                   class="caps">`` (CSS uppercases, so the source text keeps its
                   ordinary case)
- ``verse``      — set-off display line (e.g. a quoted verse), a centered block;
                   include surrounding quotation marks in the fragment so they sit
                   on the display line. The block is neutral roman; an optional
                   ``emphasis`` (``italic`` | ``bold`` | ``none``) carries the
                   line's actual 1913 slant/weight on the Italian side.

``note`` is editorial provenance and is ignored at runtime.

Verse and small-caps are emitted as private bracket sentinels (``⟦..⟧``)
rather than raw HTML so they survive ``_escape_html``; ``_para_to_html`` rewrites
them to spans. The sentinels never reach the ``.md`` files — they live only in
the in-memory paragraph string between ``apply_typography`` and HTML conversion.
"""

from __future__ import annotations

import json
from pathlib import Path

# Bracket sentinels (U+27E6 / U+27E7) — pass through _escape_html untouched and
# never occur in the source text. Rewritten to spans by typeset._para_to_html.
SC_OPEN, SC_CLOSE = "⟦sc⟧", "⟦/sc⟧"
VERSE_OPEN, VERSE_CLOSE = "⟦verse⟧", "⟦/verse⟧"
B_OPEN, B_CLOSE = "⟦b⟧", "⟦/b⟧"
I_OPEN, I_CLOSE = "⟦i⟧", "⟦/i⟧"          # scan-restored 1913 italic (distinct from translator italics)
CAPS_OPEN, CAPS_CLOSE = "⟦caps⟧", "⟦/caps⟧"
# Verse carries the 1913 line's own weight/slant; the neutral form is roman.
VERSE_I_OPEN, VERSE_I_CLOSE = "⟦verseI⟧", "⟦/verseI⟧"  # set-off line, italic
VERSE_B_OPEN, VERSE_B_CLOSE = "⟦verseB⟧", "⟦/verseB⟧"  # set-off line, bold


def load_typography(data_dir: Path) -> dict[str, list[dict]]:
    """Load the typography sidecar; return an empty map if absent."""
    path = data_dir / "typography.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _wrap(frag: str, style: str, emphasis: str = "none", lang: str = "it") -> str | None:
    """Return ``frag`` wrapped in the marker for ``style``, or ``None`` if unknown.

    ``emphasis`` (verse only) reproduces the 1913 line's actual weight/slant —
    the printer set verse variously italic-roman, plain-roman, or bold-roman, so
    the block is neutral and the slant/weight is carried per entry. It is applied
    to the Italian original (``lang == "it"``) only; the English is the
    translator's setting, whose own markdown italics survive on their own.
    """
    if style == "italic":
        return f"{I_OPEN}{frag}{I_CLOSE}"
    if style == "bold":
        return f"{B_OPEN}{frag}{B_CLOSE}"
    if style in ("small-caps", "sc"):
        return f"{SC_OPEN}{frag}{SC_CLOSE}"
    if style in ("all-caps", "caps"):
        return f"{CAPS_OPEN}{frag}{CAPS_CLOSE}"
    if style == "verse":
        if lang == "it" and emphasis == "italic":
            return f"{VERSE_I_OPEN}{frag}{VERSE_I_CLOSE}"
        if lang == "it" and emphasis == "bold":
            return f"{VERSE_B_OPEN}{frag}{VERSE_B_CLOSE}"
        return f"{VERSE_OPEN}{frag}{VERSE_CLOSE}"
    return None


def _apply_occurrences(text: str, frag: str, repl: str, occ) -> str:
    """Wrap occurrence(s) of ``frag`` in ``text`` per ``occ``.

    ``occ`` is ``"first"`` (default), ``"all"``, or an int N (1-based) selecting
    a single occurrence. ``str.replace`` does not rescan its own output, so even
    ``"all"`` cannot double-wrap (the marker contains ``frag``). Returns ``text``
    unchanged when the requested occurrence does not exist.
    """
    if occ == "all":
        return text.replace(frag, repl)
    try:
        n = 1 if occ in (None, "first") else int(occ)
    except (TypeError, ValueError):
        n = 1
    if n <= 1:
        return text.replace(frag, repl, 1)
    idx, start = -1, 0
    for _ in range(n):
        idx = text.find(frag, start)
        if idx == -1:
            return text  # fewer than n occurrences — no-op
        start = idx + len(frag)
    return text[:idx] + repl + text[idx + len(frag):]


def apply_typography(
    text: str, chapter_id: str, typo_map: dict[str, list[dict]], lang: str
) -> tuple[str, list[tuple[str, str, str]]]:
    """Inject typography markers into one paragraph's text for ``chapter_id``/``lang``.

    Matching is verbatim-substring. An entry may carry a ``<lang>_anchor`` — a
    longer verbatim context that contains ``frag`` — to disambiguate which
    occurrence to style when the same word recurs in the chapter: the target is
    wrapped only inside the first instance of that anchor. Without an anchor, the
    ``occurrences`` key controls scope (``"first"`` default, ``"all"``, or a
    1-based int). The anchor solves the no-stable-paragraph-id problem without
    positional addressing.

    Returns ``(text, applied)`` where ``applied`` lists the ``(style, fragment,
    anchor)`` triples actually marked in this paragraph (anchor is ``""`` when
    none). A fragment absent from *this* paragraph is skipped (it may live in
    another); the caller diffs accumulated ``applied`` against ``expected_spans``
    to flag entries that matched nowhere — keyed including the anchor so two
    same-word entries are tracked independently.
    """
    applied: list[tuple[str, str, str]] = []
    for entry in typo_map.get(chapter_id, []):
        frag = entry.get(lang)
        if not frag:
            continue
        style = entry.get("style", "italic")
        repl = _wrap(frag, style, entry.get("emphasis", "none"), lang)
        if repl is None:
            continue
        anchor = entry.get(f"{lang}_anchor") or ""
        occ = entry.get("occurrences", "first")
        if anchor:
            # Restrict wrapping to the first instance of the anchor context.
            start = text.find(anchor)
            if start == -1 or frag not in anchor:
                continue
            end = start + len(anchor)
            new_region = _apply_occurrences(text[start:end], frag, repl, occ)
            if new_region == text[start:end]:
                continue
            text = text[:start] + new_region + text[end:]
        else:
            if frag not in text:
                continue
            new_text = _apply_occurrences(text, frag, repl, occ)
            if new_text == text:
                continue
            text = new_text
        applied.append((style, frag, anchor))
    return text, applied


def expected_spans(
    typo_map: dict[str, list[dict]], langs: tuple[str, ...] = ("it", "en")
) -> set[tuple[str, str, str, str, str]]:
    """Every span the sidecar should place, as ``(chapter_id, lang, style, fragment, anchor)``.

    Subtract the set of spans actually applied to get the entries that matched
    no paragraph in any chapter — i.e. a stale or mis-keyed sidecar entry (or a
    bad anchor). The anchor is part of the identity so two same-word entries
    distinguished only by their anchor are tracked independently.
    """
    expected: set[tuple[str, str, str, str, str]] = set()
    for chapter_id, entries in typo_map.items():
        for entry in entries:
            style = entry.get("style", "italic")
            for lang in langs:
                frag = entry.get(lang)
                if frag:
                    anchor = entry.get(f"{lang}_anchor") or ""
                    expected.add((chapter_id, lang, style, frag, anchor))
    return expected
