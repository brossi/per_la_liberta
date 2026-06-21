"""Italian (~1900–1922) ``LanguagePlugin``.

Faithful ports of the language-specific logic the live pipeline scatters across
``utils.py`` (ordinals, heading detection, boilerplate bounds) and ``translate.py``
(title → English). The data tables are reproduced verbatim — the OCR-garble fixes
(``qyinto`` …) are observed-scan data the plugin owns, per the plan's parameterization
map (which routes all four ordinal tables here).
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from ..util.text import normalize_for_comparison
from .base import LanguagePlugin

# --- ordinal parsing (utils.py:13-69) -------------------------------------- #

ORDINALS = {
    "primo": 1, "secondo": 2, "terzo": 3, "quarto": 4, "quinto": 5,
    "sesto": 6, "settimo": 7, "ottavo": 8, "nono": 9, "decimo": 10,
    "undicesimo": 11, "dodicesimo": 12, "tredicesimo": 13,
    "quattordicesimo": 14, "quindicesimo": 15, "sedicesimo": 16,
    "decimosettimo": 17, "decimottavo": 18, "decimonono": 19,
    "ventesimo": 20, "ventesimoprimo": 21, "ventesimosecondo": 22,
    "ventesimoterzo": 23, "ventesimoquarto": 24, "ventesimoquinto": 25,
    "ventesimosesto": 26, "ventesimosettimo": 27, "ventesimottavo": 28,
    "ventesimonono": 29, "trentesimo": 30, "trentesimoprimo": 31,
    "trentesimosecondo": 32, "trentesimoterzo": 33,
}

# Known OCR garbles for ordinals (applied to the full joined string).
ORDINAL_FIXES = {
    "o^indiccsimo": "quindicesimo",
    "dccimoscttimo": "decimosettimo",
    "dccimottavo": "decimottavo",
    "qyattordicesimo": "quattordicesimo",
    "qyinto": "quinto",
    "qyarto": "quarto",
    "qtiinto": "quinto",
    "ventesìmoteizo": "ventesimoterzo",
    "decimoqyinto": "decimoquinto",
    "ventesimoqtiinto": "ventesimoquinto",
}

# Word-level OCR fixes for individual ordinal words.
WORD_FIXES = {
    "qyinto": "quinto",
    "qyarto": "quarto",
    "qtiinto": "quinto",
    "qyattordicesimo": "quattordicesimo",
}

# Compound ordinals that appear as two words.
COMPOUND_ORDINALS = {
    ("decimo", "quinto"): 15,
    ("decimo", "sesto"): 16,
    ("decimo", "settimo"): 17,
    ("decimo", "ottavo"): 18,
    ("decimo", "nono"): 19,
    ("ventesimo", "primo"): 21,
    ("ventesimo", "secondo"): 22,
    ("ventesimo", "terzo"): 23,
    ("ventesimo", "quarto"): 24,
    ("ventesimo", "quinto"): 25,
    ("ventesimo", "sesto"): 26,
    ("ventesimo", "settimo"): 27,
    ("ventesimo", "ottavo"): 28,
    ("ventesimo", "nono"): 29,
    ("trentesimo", "primo"): 31,
    ("trentesimo", "secondo"): 32,
    ("trentesimo", "terzo"): 33,
}

# "Capitolo" with OCR garbles (Gtpitolo, …). utils.py:209.
_HEADING_RE = re.compile(r"(?:[GC][a-z]*pitolo|Capitolo)\s+(.+)", re.IGNORECASE)
_HEADING_NOISE_RE = re.compile(r"[^a-zA-ZàèìòùéÀÈÌÒÙÈ\s]")

# --- title → English (translate.py:297-361) -------------------------------- #

_ITALIAN_NUMBERS = {
    "Primo": "One", "Secondo": "Two", "Terzo": "Three", "Quarto": "Four",
    "Quinto": "Five", "Sesto": "Six", "Settimo": "Seven", "Ottavo": "Eight",
    "Nono": "Nine", "Decimo": "Ten", "Undicesimo": "Eleven",
    "Dodicesimo": "Twelve", "Tredicesimo": "Thirteen",
    "Quattordicesimo": "Fourteen", "Quindicesimo": "Fifteen",
    "Sedicesimo": "Sixteen", "Diciassettesimo": "Seventeen",
    "Diciottesimo": "Eighteen", "Diciannovesimo": "Nineteen",
    "Ventesimo": "Twenty", "Ventesimoterzo": "Twenty-Three",
    "Ventesimoquarto": "Twenty-Four", "Trentesimo": "Thirty",
    "O^indiccsimo": "Eleven",
    "Dccimoscttimo": "Seventeen",
    "Dccimottavo": "Eighteen",
    "Decimonono": "Nineteen",
}

_ITALIAN_ORDINAL_PARTS = {
    "Decimo": "Ten", "Ventesimo": "Twenty", "Trentesimo": "Thirty",
    "Primo": "One", "Secondo": "Two", "Terzo": "Three", "Quarto": "Four",
    "Quinto": "Five", "Sesto": "Six", "Settimo": "Seven", "Ottavo": "Eight",
    "Nono": "Nine",
}

_TEENS = {
    ("Ten", "One"): "Eleven", ("Ten", "Two"): "Twelve",
    ("Ten", "Three"): "Thirteen", ("Ten", "Four"): "Fourteen",
    ("Ten", "Five"): "Fifteen", ("Ten", "Six"): "Sixteen",
    ("Ten", "Seven"): "Seventeen", ("Ten", "Eight"): "Eighteen",
    ("Ten", "Nine"): "Nineteen",
}

_STRUCTURAL_EN = {
    "Prefazione": "Preface",
    "Parte Prima": "Part One",
    "Parte Seconda": "Part Two",
}

# Part headers → (short_code, part_number, canonical_title).
_PARTS = {
    "Parte Prima": ("p1", 1, "Parte Prima"),
    "Parte Seconda": ("p2", 2, "Parte Seconda"),
}


class ItalianLanguagePlugin(LanguagePlugin):
    language_id = "it"

    # --- recognition hooks ------------------------------------------------- #
    def structural_part(self, title: str) -> tuple[str, int, str] | None:
        return _PARTS.get(title.strip())

    def title_to_english(self, title: str) -> str:
        """Port of translate._italian_to_english_title."""
        if title in _STRUCTURAL_EN:
            return _STRUCTURAL_EN[title]

        m = re.match(r"Capitolo\s+(.+)", title)
        if not m:
            return title
        rest = m.group(1).strip()

        if rest in _ITALIAN_NUMBERS:
            return f"Chapter {_ITALIAN_NUMBERS[rest]}"

        parts = rest.split()
        if (
            len(parts) == 2
            and parts[0] in _ITALIAN_ORDINAL_PARTS
            and parts[1] in _ITALIAN_ORDINAL_PARTS
        ):
            tens = _ITALIAN_ORDINAL_PARTS[parts[0]]
            ones = _ITALIAN_ORDINAL_PARTS[parts[1]]
            teen = _TEENS.get((tens, ones))
            if teen:
                return f"Chapter {teen}"
            return f"Chapter {tens}-{ones}"

        return f"Chapter {rest}"

    def parse_chapter_number(self, words: Sequence[str]) -> int | None:
        """Port of utils._parse_chapter_number."""
        if not words:
            return None

        joined = "".join(w.lower() for w in words)

        for garble, fix in ORDINAL_FIXES.items():
            if normalize_for_comparison(joined) == normalize_for_comparison(garble):
                joined = fix
                break

        normalized = normalize_for_comparison(joined)
        for ordinal, num in ORDINALS.items():
            if normalize_for_comparison(ordinal) == normalized:
                return num

        if len(words) >= 2:
            w1 = normalize_for_comparison(words[0])
            w2_raw = words[1].lower().strip()
            w2_fixed = WORD_FIXES.get(w2_raw, w2_raw)
            w2 = normalize_for_comparison(w2_fixed)
            for (o1, o2), num in COMPOUND_ORDINALS.items():
                if (
                    normalize_for_comparison(o1) == w1
                    and normalize_for_comparison(o2) == w2
                ):
                    return num

        w1_norm = normalize_for_comparison(words[0])
        for ordinal, num in ORDINALS.items():
            if normalize_for_comparison(ordinal) == w1_norm:
                return num

        return None

    def is_chapter_heading(self, line: str) -> tuple[int, str] | None:
        """Port of utils._is_chapter_heading."""
        stripped = re.sub(r"\s+", " ", line.strip())
        match = _HEADING_RE.match(stripped)
        if not match:
            return None
        rest = _HEADING_NOISE_RE.sub("", match.group(1).strip()).strip()
        if not rest:
            return None
        num = self.parse_chapter_number(rest.split())
        if num is not None:
            return (num, stripped)
        return None

    def strip_boilerplate(self, text: str) -> str:
        """Port of utils.strip_boilerplate — keep PREFAZIONE … INDICE."""
        lines = text.split("\n")
        start = 0
        for i, line in enumerate(lines):
            if re.match(r"\s*PREFAZIONE\s*$", line):
                start = i
                break
        end = len(lines)
        for i in range(len(lines) - 1, -1, -1):
            if re.match(r"\s*INDICE\s*$", lines[i]):
                end = i
                break
        return "\n".join(lines[start:end])
