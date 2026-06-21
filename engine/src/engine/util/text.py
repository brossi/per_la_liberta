"""Generic text normalisation — ported verbatim from the top-level utils.py.

Nothing here is language-specific: accent stripping is Unicode-general and slugging
is pure string mechanics. The Italian-specific pieces (ordinals, heading keywords)
live in ``engine.lang.italian``.
"""

from __future__ import annotations

import re
import unicodedata


def strip_accents(text: str) -> str:
    """Remove combining accents (NFKD decomposition). utils.strip_accents."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_for_comparison(text: str) -> str:
    """Lowercase, strip accents, drop non-[a-z]. utils.normalize_for_comparison.

    The accent-insensitive comparison key used for ordinal/heading matching.
    """
    text = strip_accents(text.lower())
    return re.sub(r"[^a-z]", "", text)


def collapse_spaces(text: str) -> str:
    """Collapse runs of spaces to one. utils.collapse_spaces."""
    return re.sub(r"  +", " ", text)


def slug(text: str, sep: str) -> str:
    """Slugify ``text`` with the given separator.

    The single mechanic behind two of the three chapter-id namespaces:
      - ``sep="_"`` reproduces ``translate.parse_italian_markdown`` base ids;
      - ``sep="-"`` reproduces ``typeset._slug`` HTML-anchor ids.
    Both are ``re.sub(r"[^a-z0-9]", sep, text.lower()).strip(sep)``.
    """
    return re.sub(r"[^a-z0-9]", sep, text.lower()).strip(sep)
