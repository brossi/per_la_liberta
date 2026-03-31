"""Edgren 1901 Italian-English Dictionary — download, chunk, and lookup.

Provides period-appropriate English definitions for Italian words, used by
translate.py (prompt enrichment) and refine.py (post-hoc revision). Complements
Zingarelli 1922, which validates Italian word existence.

Source: Edgren Italian-English Dictionary (1901), Internet Archive OCR.
"""

import json
import re
from pathlib import Path

import requests

DICT_DIR = Path(__file__).parent / "assets" / "dictionary" / "edgren_1901"
RAW_FILE = DICT_DIR / "raw.txt"
INDEX_FILE = DICT_DIR / "index.json"
HEADWORDS_FILE = DICT_DIR / "headwords.json"

SOURCE_URL = (
    "https://archive.org/download/cu31924019173982/cu31924019173982_djvu.txt"
)

# Letter section boundaries (1-indexed line numbers in raw.txt).
# Determined by manual inspection of the OCR text: standalone letter markers
# where present, first headword of each letter where markers were missing.
# Appendices (geographical names, etc.) begin after Z at ~line 96440.
_LETTER_BOUNDARIES = {
    "A": 2191, "B": 10409, "C": 14363, "D": 23519,
    "E": 27897, "F": 30101, "G": 34093, "H": 37844,
    "I": 37855, "K": 47078, "L": 47086, "M": 49754,
    "N": 54665, "O": 55999, "P": 57902, "Q": 65661,
    "R": 66110, "S": 73713, "T": 88382, "U": 92445,
    "V": 93104, "Z": 95869,
}
_APPENDIX_LINE = 96440

# Regex for identifying headword entries in the OCR text.
# Matches: line-initial word (possibly hyphenated) followed by comma, bracket, or paren.
# Examples: "abbaco, M.:", "cabina [Eng. cabin], F.:", "libertà, F.:"
_HEADWORD_RE = re.compile(
    r"^([a-zàèéìòùA-ZÀÈÉÌÒÙ][a-zàèéìòù-]{1,30})\s*[,\[\(]"
)

# Cache for loaded chunks and headword lists
_chunks_cache: dict[str, str] = {}
_headwords_cache: dict[str, list[str]] = {}
_nlp = None  # lazy-loaded spaCy model


def _get_nlp():
    """Lazy-load spaCy Italian model."""
    global _nlp
    if _nlp is None:
        import spacy
        _nlp = spacy.load("it_core_news_lg")
    return _nlp


def _lemmatize(word: str) -> str:
    """Reduce an Italian word to its lemma."""
    nlp = _get_nlp()
    doc = nlp(word)
    return doc[0].lemma_ if doc else word


# ── Download ──────────────────────────────────────────────────────────

def download_edgren() -> Path:
    """Download the Edgren 1901 dictionary if not already present."""
    DICT_DIR.mkdir(parents=True, exist_ok=True)
    if RAW_FILE.exists() and RAW_FILE.stat().st_size > 1_000_000:
        return RAW_FILE
    print(f"  Downloading Edgren 1901 dictionary from Internet Archive...")
    resp = requests.get(SOURCE_URL, timeout=120)
    resp.raise_for_status()
    RAW_FILE.write_text(resp.text, encoding="utf-8")
    print(f"  Saved {RAW_FILE.stat().st_size:,} bytes to {RAW_FILE}")
    return RAW_FILE


# ── Chunking ──────────────────────────────────────────────────────────

def chunk_edgren() -> None:
    """Split the raw dictionary into per-letter chunks and extract headwords.

    Idempotent — skips if index.json already exists.
    """
    if INDEX_FILE.exists():
        return

    if not RAW_FILE.exists():
        download_edgren()

    print("  Chunking Edgren 1901 dictionary by letter...")
    lines = RAW_FILE.read_text(encoding="utf-8").split("\n")

    sorted_letters = sorted(_LETTER_BOUNDARIES.keys())
    all_headwords: dict[str, list[str]] = {}
    index: dict[str, dict] = {
        "_source": "Edgren, Italian and English Dictionary, 1901",
        "_note": "OCR text from Internet Archive (cu31924019173982_djvu.txt). Chunked by letter.",
        "chunks": {},
    }

    for idx, letter in enumerate(sorted_letters):
        # Convert 1-indexed line numbers to 0-indexed
        start = _LETTER_BOUNDARIES[letter] - 1
        if idx + 1 < len(sorted_letters):
            end = _LETTER_BOUNDARIES[sorted_letters[idx + 1]] - 1
        else:
            end = _APPENDIX_LINE - 1
        chunk_lines = lines[start:end]
        chunk_text = "\n".join(chunk_lines)

        # Write chunk file
        chunk_path = DICT_DIR / f"{letter.lower()}.txt"
        chunk_path.write_text(chunk_text, encoding="utf-8")

        # Extract headwords from this chunk
        headwords = []
        for line in chunk_lines:
            m = _HEADWORD_RE.match(line.strip())
            if m:
                hw = m.group(1).lower()
                if len(hw) >= 2 and hw not in headwords:
                    headwords.append(hw)

        all_headwords[letter.lower()] = headwords
        index["chunks"][letter] = {
            "file": f"{letter.lower()}.txt",
            "lines": len(chunk_lines),
            "size_kb": round(len(chunk_text) / 1024, 1),
            "headwords": len(headwords),
        }
        print(f"    {letter}: {len(chunk_lines):,} lines, {len(headwords)} headwords")

    # Write index and headwords
    INDEX_FILE.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    HEADWORDS_FILE.write_text(json.dumps(all_headwords, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Wrote index to {INDEX_FILE}")
    print(f"  Wrote headwords to {HEADWORDS_FILE}")


# ── Lookup ────────────────────────────────────────────────────────────

def _load_chunk(letter: str) -> str:
    """Load a letter chunk, caching in memory."""
    letter = letter.lower()
    if letter not in _chunks_cache:
        path = DICT_DIR / f"{letter}.txt"
        if path.exists():
            _chunks_cache[letter] = path.read_text(encoding="utf-8")
        else:
            _chunks_cache[letter] = ""
    return _chunks_cache[letter]


def _load_headwords(letter: str) -> list[str]:
    """Load headwords for a letter, caching in memory."""
    letter = letter.lower()
    if letter not in _headwords_cache:
        if not HEADWORDS_FILE.exists():
            chunk_edgren()
        data = json.loads(HEADWORDS_FILE.read_text(encoding="utf-8"))
        # Load all letters at once
        for k, v in data.items():
            _headwords_cache[k] = v
    return _headwords_cache.get(letter, [])


def _extract_entry(headword: str, chunk_text: str, context_lines: int = 8) -> str:
    """Extract the dictionary entry for a headword from the chunk text.

    Returns the matched line plus continuation lines (up to the next headword
    or context_lines, whichever comes first).
    """
    # Find the line containing this headword
    pattern = re.compile(
        r"(?<![a-zA-ZÀ-ÿ])" + re.escape(headword) + r"\s*[,\[\(]",
        re.IGNORECASE,
    )
    lines = chunk_text.split("\n")
    for i, line in enumerate(lines):
        if pattern.match(line.strip()):
            # Collect this line plus continuations
            entry_lines = [line.strip()]
            for j in range(i + 1, min(i + context_lines + 1, len(lines))):
                next_line = lines[j].strip()
                if not next_line:
                    continue
                # Stop at next headword
                if _HEADWORD_RE.match(next_line):
                    break
                entry_lines.append(next_line)
            return " ".join(entry_lines)
    return ""


_ACCENT_MAP = str.maketrans(
    "àáâèéêìíîòóôùúû", "aaaeeeiiiooouu" + "u"
)


def _normalize_for_lookup(word: str) -> str:
    """Normalize a word for headword matching."""
    return word.lower().translate(_ACCENT_MAP)


def _search_chunk_for_word(word: str, chunk_text: str, context_lines: int = 12) -> str | None:
    """Search for a word in chunk text, tolerant of dictionary abbreviations.

    The Edgren dictionary compresses entries using hyphens and accent marks:
    'libertà' appears as 'libér-ta' in the OCR. We build a regex that allows
    hyphens, spaces, and accent variants between each character of the
    normalized word, so 'liberta' matches 'libér-ta', 'liberta', etc.
    """
    if not word or not chunk_text or len(word) < 3:
        return None

    normalized = _normalize_for_lookup(word)

    # Build a flexible pattern: each char can be followed by optional
    # hyphens/spaces/accents. Also allow accented variants of each char.
    _ACCENT_VARIANTS = {
        "a": "[aàáâ]", "e": "[eèéê]", "i": "[iìíî]",
        "o": "[oòóô]", "u": "[uùúû]",
    }
    parts = []
    for ch in normalized:
        variant = _ACCENT_VARIANTS.get(ch, re.escape(ch))
        parts.append(variant)
    # Allow optional hyphen/space between each character
    flexible_pattern = r"[-\s]*".join(parts)

    pattern = re.compile(flexible_pattern, re.IGNORECASE)
    lines = chunk_text.split("\n")

    # Search pairs of adjacent lines joined together (handles entries split
    # across line breaks, e.g. '||fug-\ngire' for 'fuggire')
    for i in range(len(lines)):
        # Try single line and joined with next line
        window = lines[i]
        if i + 1 < len(lines):
            window = lines[i] + " " + lines[i + 1]
        if pattern.search(window):
            start = max(0, i - 2)
            entry_lines = []
            for j in range(start, min(i + context_lines, len(lines))):
                text = lines[j].strip()
                if text:
                    entry_lines.append(text)
            return " ".join(entry_lines)

    return None


def edgren_lookup(word: str, context_lines: int = 8) -> str | None:
    """Look up an Italian word in the Edgren 1901 dictionary.

    Lemmatizes the word first, then tries:
    1. Exact headword match
    2. Flexible text search (handles dictionary abbreviations like 'libér-ta' for 'libertà')
    3. Fuzzy headword fallback (catches OCR-garbled headwords)

    Returns the raw dictionary entry text, or None if not found.
    """
    from rapidfuzz import process as rfprocess

    if not word or len(word) < 2:
        return None

    if not INDEX_FILE.exists():
        chunk_edgren()

    lemma = _lemmatize(word)
    candidates = [lemma, word] if lemma != word else [word]

    for candidate in candidates:
        normalized = _normalize_for_lookup(candidate)
        if not normalized or not normalized[0].isalpha():
            continue

        letter = normalized[0]
        chunk_text = _load_chunk(letter)
        if not chunk_text:
            continue

        # Strategy 1: exact headword match
        headwords = _load_headwords(letter)
        if normalized in headwords:
            entry = _extract_entry(normalized, chunk_text, context_lines)
            if entry:
                return entry

        # Strategy 2: flexible text search (handles dictionary abbreviations
        # like 'libér-ta' for 'libertà', sub-entries, etc.)
        entry = _search_chunk_for_word(candidate, chunk_text, context_lines)
        if entry:
            return entry

        # Strategy 3: fuzzy headword match (fallback for OCR-garbled headwords)
        if headwords:
            min_len = max(3, len(normalized) // 2)
            filtered = [hw for hw in headwords if len(hw) >= min_len]
            if filtered:
                match = rfprocess.extractOne(
                    normalized, filtered, score_cutoff=88
                )
                if match:
                    entry = _extract_entry(match[0], chunk_text, context_lines)
                    if entry:
                        return entry

    return None


def edgren_entries_for_words(words: list[str]) -> dict[str, str]:
    """Batch lookup: map Italian words to their Edgren dictionary entries.

    Returns a dict of {word: entry_text} for words that have entries.
    Omits words with no match.
    """
    results = {}
    for word in words:
        entry = edgren_lookup(word)
        if entry:
            results[word] = entry
    return results


# ── Vocabulary extraction ─────────────────────────────────────────────

# POS tags for semantically significant content words
_CONTENT_POS = {"NOUN", "VERB", "ADJ", "ADV"}


def extract_content_words(text: str) -> list[str]:
    """Extract semantically significant Italian words from text.

    Returns deduplicated list of lemmas for nouns, verbs, adjectives, adverbs.
    Skips function words (determiners, prepositions, conjunctions, etc.).
    """
    nlp = _get_nlp()
    doc = nlp(text)

    seen = set()
    words = []
    for token in doc:
        if token.pos_ not in _CONTENT_POS:
            continue
        if token.is_stop or token.is_punct or token.is_space:
            continue
        lemma = token.lemma_.lower()
        if len(lemma) < 3 or lemma in seen:
            continue
        seen.add(lemma)
        words.append(lemma)

    return words


def format_edgren_context(entries: dict[str, str], max_entries: int = 50) -> str:
    """Format Edgren entries as a reference block for LLM prompts.

    Returns a formatted string suitable for inclusion in translation/refinement
    prompts. Caps at max_entries to avoid prompt bloat.
    """
    if not entries:
        return ""

    items = list(entries.items())[:max_entries]
    lines = []
    for word, entry in items:
        # Truncate very long entries
        if len(entry) > 200:
            entry = entry[:200] + "..."
        lines.append(f"  {word}: {entry}")

    return (
        "=== Edgren Italian-English Dictionary (1901) ===\n"
        + "\n".join(lines)
        + "\n=== End Dictionary Reference ===\n"
    )


# ── CLI ───────────────────────────────────────────────────────────────

def main():
    """Download, chunk, and test lookup."""
    download_edgren()
    chunk_edgren()

    # Test lookups
    test_words = [
        "libertà", "patria", "rivoluzione", "coraggio", "tradimento",
        "scuotere", "fuggire", "popolo", "governo", "giustizia",
    ]
    print("\n  Test lookups:")
    for word in test_words:
        entry = edgren_lookup(word)
        if entry:
            display = entry[:100] + "..." if len(entry) > 100 else entry
            print(f"    {word:15s} → {display}")
        else:
            print(f"    {word:15s} → NOT FOUND")


if __name__ == "__main__":
    main()
