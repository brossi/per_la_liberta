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
span. ``style`` is one of:

- ``italic``     — inline emphasis -> markdown ``*...*`` -> ``<em>``
- ``small-caps`` — inline small capitals -> ``<span class="sc">``
- ``verse``      — set-off display line (e.g. a quoted verse), rendered as a
                   centered italic block; include surrounding quotation marks in
                   the fragment so they sit on the display line, not orphaned.

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


def load_typography(data_dir: Path) -> dict[str, list[dict]]:
    """Load the typography sidecar; return an empty map if absent."""
    path = data_dir / "typography.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def apply_typography(
    text: str, chapter_id: str, typo_map: dict[str, list[dict]], lang: str
) -> tuple[str, list[tuple[str, str]]]:
    """Inject typography markers into one paragraph's text for ``chapter_id``/``lang``.

    Matching is verbatim-substring; the first occurrence of each fragment is
    wrapped. Returns ``(text, applied)`` where ``applied`` is the list of
    ``(style, fragment)`` actually marked in this paragraph. A fragment absent
    from *this* paragraph is simply skipped (it may live in another paragraph);
    the caller compares accumulated ``applied`` against the full sidecar to
    detect fragments that matched nowhere (see ``expected_spans``).
    """
    applied: list[tuple[str, str]] = []
    for entry in typo_map.get(chapter_id, []):
        frag = entry.get(lang)
        if not frag:
            continue
        style = entry.get("style", "italic")
        if frag not in text:
            continue
        if style == "italic":
            repl = f"*{frag}*"
        elif style in ("small-caps", "sc"):
            repl = f"{SC_OPEN}{frag}{SC_CLOSE}"
        elif style == "verse":
            repl = f"{VERSE_OPEN}{frag}{VERSE_CLOSE}"
        else:
            continue
        text = text.replace(frag, repl, 1)
        applied.append((style, frag))
    return text, applied


def expected_spans(
    typo_map: dict[str, list[dict]], langs: tuple[str, ...] = ("it", "en")
) -> set[tuple[str, str, str, str]]:
    """Every span the sidecar should place, as ``(chapter_id, lang, style, fragment)``.

    Subtract the set of spans actually applied to get the fragments that matched
    no paragraph in any chapter — i.e. a stale or mis-keyed sidecar entry.
    """
    expected: set[tuple[str, str, str, str]] = set()
    for chapter_id, entries in typo_map.items():
        for entry in entries:
            style = entry.get("style", "italic")
            for lang in langs:
                frag = entry.get(lang)
                if frag:
                    expected.add((chapter_id, lang, style, frag))
    return expected
