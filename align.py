"""Paragraph-level English↔Italian alignment for the intention-review track.

The translation is per-chapter and paragraph-by-paragraph, so chapters align
positionally — but only 38 of 58 have an exact 1:1 paragraph count; the rest
drift where the translator split or merged a paragraph, and one early split
throws off every later index. So same-index lookup is unsafe.

This aligns each chapter's English and Italian paragraph sequences with a
monotonic DP (Needleman–Wunsch-style) scored on translation-INVARIANT tokens —
years, multi-digit numbers, and capitalized-word prefixes (Orsini, Napoleon↔
Napoleone, Milan↔Milano). Those survive translation; ordinary words don't.
Validated: reproduces same-index on 100% of the 1,245 passages in exact-match
chapters, and on drifted chapters lands on the correct paragraph (or, for a
split, an adjacent one — hence callers should take a ±1 window).

Confidence is the matched pair's invariant-token Jaccard; it is a SOFT signal,
not a gate — short passages with no shared proper nouns align correctly by
position at confidence 0.

    from align import italian_window
    w = italian_window("p2_capitolo_quattordicesimo", 43)   # -> {it_idx, conf, drift, text}
"""

import re

from comprehension import ENGLISH_MD, chapter_slugs, parse_english
from translate import parse_italian_markdown

ITALIAN_MD = "output/italian_clean.md"

_YEAR = re.compile(r"\b1[78]\d\d\b")
_NUM = re.compile(r"\b\d{2,}\b")
_CAP = re.compile(r"\b([A-ZÀ-Þ][a-zà-ÿ]{2,})\b")
_GAP = 0.05  # per-paragraph gap penalty (a split/merge costs less than a bad match)


def _it_paras(text: str) -> list[str]:
    """Italian chapter body → paragraph list, dropping page-marker comments."""
    return [p.strip() for p in re.split(r"\n\s*\n", text)
            if p.strip() and not p.strip().startswith("<!--")]


def _invariants(s: str) -> set[str]:
    return (set(_YEAR.findall(s)) | set(_NUM.findall(s))
            | {w[:4].lower() for w in _CAP.findall(s)})


def _sim(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def _align_chapter(en_ps: list[str], it_ps: list[str]) -> dict[int, tuple[int, float]]:
    """Monotonic DP alignment; returns {en_idx: (it_idx, confidence)}."""
    ei = [_invariants(p) for p in en_ps]
    ii = [_invariants(p) for p in it_ps]
    n, m = len(en_ps), len(it_ps)
    NEG = float("-inf")
    dp = [[NEG] * (m + 1) for _ in range(n + 1)]
    bk: list[list] = [[None] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0
    for i in range(n + 1):
        for j in range(m + 1):
            if dp[i][j] == NEG:
                continue
            if i < n and j < m:  # match en[i] ↔ it[j]
                v = dp[i][j] + _sim(ei[i], ii[j])
                if v > dp[i + 1][j + 1]:
                    dp[i + 1][j + 1] = v
                    bk[i + 1][j + 1] = ("M", i, j)
            if i < n and dp[i][j] - _GAP > dp[i + 1][j]:  # en gap (merge)
                dp[i + 1][j] = dp[i][j] - _GAP
                bk[i + 1][j] = ("E", i, j)
            if j < m and dp[i][j] - _GAP > dp[i][j + 1]:  # it gap (split)
                dp[i][j + 1] = dp[i][j] - _GAP
                bk[i][j + 1] = ("I", i, j)
    out: dict[int, tuple[int, float]] = {}
    i, j = n, m
    while (i, j) != (0, 0):
        op, pi, pj = bk[i][j]
        if op == "M":
            out[pi] = (pj, _sim(ei[pi], ii[pj]))
        elif op == "E":  # merged en paragraph: point at the nearest it paragraph
            out[pi] = (min(pj, m - 1), 0.0)
        i, j = pi, pj
    return out


_cache: dict[str, tuple[dict[int, tuple[int, float]], list[str]]] = {}


def _chapter(slug: str) -> tuple[dict[int, tuple[int, float]], list[str]]:
    if slug not in _cache:
        en = dict(zip(chapter_slugs(), parse_english(open(ENGLISH_MD, encoding="utf-8").read())))
        it = {c["id"]: c for c in parse_italian_markdown(open(ITALIAN_MD, encoding="utf-8").read())
              if not c.get("is_structural")}
        en_ps = en[slug]["passages"]
        it_ps = _it_paras(it[slug]["text"])
        _cache[slug] = (_align_chapter(en_ps, it_ps), it_ps)
    return _cache[slug]


def italian_window(slug: str, en_idx: int, radius: int = 1) -> dict | None:
    """Italian source for an English passage, as a ±radius paragraph window.

    Returns {it_idx, conf, drift, text} where text joins the matched paragraph
    with `radius` neighbours on each side (absorbs paragraph-split drift), or
    None if the chapter/passage can't be resolved.
    """
    try:
        mapping, it_ps = _chapter(slug)
    except KeyError:
        return None
    if en_idx not in mapping:
        return None
    it_idx, conf = mapping[en_idx]
    lo, hi = max(0, it_idx - radius), min(len(it_ps), it_idx + radius + 1)
    return {"it_idx": it_idx, "conf": round(conf, 2), "drift": en_idx - it_idx,
            "text": "\n\n".join(it_ps[lo:hi])}
