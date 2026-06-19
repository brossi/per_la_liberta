"""Hoare 1915 Italian Dictionary — download, chunk, and lookup.

Alfred Hoare, *An Italian Dictionary* (Cambridge University Press, 1915) — a
period-appropriate authority published two years after the 1913 source text,
strong on archaic/literary and technical vocabulary. Public domain
(Internet Archive marks the item NOT_IN_COPYRIGHT). Used as the third
membership oracle alongside Zingarelli 1922 (adjudicate.zingarelli_lookup) and
Edgren 1901 (edgren.edgren_lookup): a word found in two or more of the three is
confidently a real period word, which is what separates a cleanup *corruption*
of a valid 1913 form from a legitimate fix of OCR garble.

The OCR has two parts in one file:
  - main Italian->English body (line-initial Capitalized, often accented Italian
    headwords: "Boiardo m.; ...", "Eclissàre ..."), lines ~993..217644;
  - an English->Italian index at the back (English headwords, Italian glosses:
    "Outshine ; eclissare."), lines 217645..end.
The body is chunked by the headword's own first letter (robust to OCR ordering
glitches); the back index is kept whole and searched as a fallback, because
infinitives the body carries accented often appear there as clean glosses.

Source: https://archive.org/details/italiandictionar00hoaruoft
"""

import json
import re
from pathlib import Path

import requests

DICT_DIR = Path(__file__).parent / "assets" / "dictionary" / "hoare_1915"
RAW_FILE = DICT_DIR / "raw.txt"
INDEX_FILE = DICT_DIR / "index.json"
HEADWORDS_FILE = DICT_DIR / "headwords.json"
INDEX_CHUNK = "en_index.txt"  # English->Italian back index, kept whole

SOURCE_URL = (
    "https://archive.org/download/italiandictionar00hoaruoft/"
    "italiandictionar00hoaruoft_djvu.txt"
)

# 1-indexed line numbers in raw.txt, from inspection of the OCR:
# front matter ends and the "A" body begins ~993; the English-Italian index
# (which would otherwise re-introduce A-Z English headwords) begins at 217645.
_BODY_START = 993
_BACK_INDEX = 217645

# Line-initial Capitalized Italian headword, optional obsolete/local marker,
# followed by a gender mark / punctuation that opens the entry.
_HEADWORD_RE = re.compile(
    r"^[*†‡•]?\s*([A-ZÀÈÉÌÒÙ][A-Za-zàèéìòù\-]{1,28})\s*[mf/.;,\[(]"
)

_chunks_cache: dict[str, str] = {}
_headwords_cache: dict[str, list[str]] = {}
_nlp = None


def _get_nlp():
    global _nlp
    if _nlp is None:
        import spacy
        _nlp = spacy.load("it_core_news_lg")
    return _nlp


def _lemmatize(word: str) -> str:
    nlp = _get_nlp()
    doc = nlp(word)
    return doc[0].lemma_ if doc else word


# ── Download ──────────────────────────────────────────────────────────

def download_hoare() -> Path:
    """Download the Hoare 1915 dictionary OCR text if not already present."""
    DICT_DIR.mkdir(parents=True, exist_ok=True)
    if RAW_FILE.exists() and RAW_FILE.stat().st_size > 1_000_000:
        return RAW_FILE
    print("  Downloading Hoare 1915 dictionary from Internet Archive...")
    resp = requests.get(SOURCE_URL, timeout=180)
    resp.raise_for_status()
    RAW_FILE.write_text(resp.text, encoding="utf-8")
    print(f"  Saved {RAW_FILE.stat().st_size:,} bytes to {RAW_FILE}")
    return RAW_FILE


# ── Chunking ──────────────────────────────────────────────────────────

_DEACCENT = str.maketrans("àáâãäèéêëìíîïòóôõöùúûü", "aaaaaeeeeiiiiooooouuuu")


def _first_letter(word: str) -> str:
    return word[:1].lower().translate(_DEACCENT)


def chunk_hoare() -> None:
    """Bin the Italian->English body by headword letter; keep the back index whole.

    Idempotent — skips if index.json already exists.
    """
    if INDEX_FILE.exists():
        return
    if not RAW_FILE.exists():
        download_hoare()

    print("  Chunking Hoare 1915 dictionary...")
    lines = RAW_FILE.read_text(encoding="utf-8").split("\n")
    body = lines[_BODY_START - 1:_BACK_INDEX - 1]
    back = lines[_BACK_INDEX - 1:]

    buckets: dict[str, list[str]] = {chr(c): [] for c in range(ord("a"), ord("z") + 1)}
    headwords: dict[str, list[str]] = {k: [] for k in buckets}
    current = None
    for ln in body:
        m = _HEADWORD_RE.match(ln.strip())
        if m:
            letter = _first_letter(m.group(1))
            if letter in buckets:
                current = letter
                hw = m.group(1).lower()
                if hw not in headwords[letter]:
                    headwords[letter].append(hw)
        if current:
            buckets[current].append(ln)

    index: dict = {
        "_source": "Hoare, An Italian Dictionary, Cambridge Univ. Press, 1915",
        "_copyright": "public domain (Internet Archive: NOT_IN_COPYRIGHT)",
        "_note": ("OCR text from Internet Archive "
                  "(italiandictionar00hoaruoft_djvu.txt). Italian->English body "
                  "binned by headword letter; English->Italian back index kept "
                  "whole as en_index.txt."),
        "chunks": {},
    }
    for letter in sorted(buckets):
        text = "\n".join(buckets[letter])
        (DICT_DIR / f"{letter}.txt").write_text(text, encoding="utf-8")
        index["chunks"][letter.upper()] = {
            "file": f"{letter}.txt",
            "lines": len(buckets[letter]),
            "size_kb": round(len(text) / 1024, 1),
            "headwords": len(headwords[letter]),
        }
        print(f"    {letter.upper()}: {len(buckets[letter]):,} lines, "
              f"{len(headwords[letter])} headwords")

    back_text = "\n".join(back)
    (DICT_DIR / INDEX_CHUNK).write_text(back_text, encoding="utf-8")
    index["chunks"]["_INDEX"] = {
        "file": INDEX_CHUNK,
        "lines": len(back),
        "size_kb": round(len(back_text) / 1024, 1),
        "note": "English->Italian vocabulary (searched as fallback)",
    }

    INDEX_FILE.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    HEADWORDS_FILE.write_text(json.dumps(headwords, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Wrote index to {INDEX_FILE}")


# ── Lookup ────────────────────────────────────────────────────────────

def _load_chunk(letter: str) -> str:
    if letter not in _chunks_cache:
        path = DICT_DIR / (INDEX_CHUNK if letter == "_index" else f"{letter}.txt")
        _chunks_cache[letter] = path.read_text(encoding="utf-8") if path.exists() else ""
    return _chunks_cache[letter]


def _load_headwords(letter: str) -> list[str]:
    if not _headwords_cache:
        if not HEADWORDS_FILE.exists():
            chunk_hoare()
        _headwords_cache.update(json.loads(HEADWORDS_FILE.read_text(encoding="utf-8")))
    return _headwords_cache.get(letter, [])


_ACCENT_VARIANTS = {
    "a": "[aàáâ]", "e": "[eèéê]", "i": "[iìíî]", "o": "[oòóô]", "u": "[uùúû]",
}


def _normalize(word: str) -> str:
    return word.lower().translate(_DEACCENT)


def _search_chunk(word: str, chunk_text: str, context_lines: int = 8) -> str | None:
    """Flexible accent/hyphen-tolerant search (Hoare OCR breaks words with
    hyphens and accents, e.g. 'Eclissà-re'). Mirrors edgren._search_chunk_for_word."""
    if not word or not chunk_text or len(word) < 3:
        return None
    parts = [_ACCENT_VARIANTS.get(ch, re.escape(ch)) for ch in _normalize(word)]
    pattern = re.compile(r"[-\s]*".join(parts), re.IGNORECASE)
    lines = chunk_text.split("\n")
    for i in range(len(lines)):
        window = lines[i] + (" " + lines[i + 1] if i + 1 < len(lines) else "")
        if pattern.search(window):
            start = max(0, i - 1)
            entry = [lines[j].strip() for j in range(start, min(i + context_lines, len(lines))) if lines[j].strip()]
            return " ".join(entry)
    return None


def hoare_lookup(word: str, context_lines: int = 8) -> str | None:
    """Look up an Italian word in Hoare 1915.

    Lemmatizes, then tries the word's letter chunk (flexible search) and finally
    the English->Italian back index. Returns the raw entry text, or None.
    """
    if not word or len(word) < 2:
        return None
    if not INDEX_FILE.exists():
        chunk_hoare()

    lemma = _lemmatize(word)
    candidates = [word, lemma] if lemma != word else [word]
    for cand in candidates:
        norm = _normalize(cand)
        if not norm or not norm[0].isalpha():
            continue
        for chunk_key in (norm[0], "_index"):
            entry = _search_chunk(cand, _load_chunk(chunk_key), context_lines)
            if entry:
                return entry
    return None


def hoare_contains(word: str) -> bool:
    """Membership test: is `word` a real period word per Hoare 1915?"""
    return hoare_lookup(word) is not None


# ── CLI ───────────────────────────────────────────────────────────────

def main():
    download_hoare()
    chunk_hoare()
    tests = ["libertà", "patria", "eclissare", "foggiare", "arguire",
             "moltiplicare", "sfavillare", "seppellire", "boia", "alterezza",
             "qualche", "cielo"]
    print("\n  Test lookups:")
    for w in tests:
        e = hoare_lookup(w)
        print(f"    {w:14s} -> {(e[:80] + '...') if e and len(e) > 80 else (e or 'NOT FOUND')}")


if __name__ == "__main__":
    main()
