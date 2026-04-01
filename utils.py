"""Shared utilities: chapter parsing, text normalization, boilerplate stripping."""

import json
import os
import re
import tempfile
import time
import unicodedata
from pathlib import Path


# Canonical Italian ordinals for chapter numbers 1-33
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

# Known OCR garbles for ordinals (both copies)
# Applied to full joined string and individual words
ORDINAL_FIXES = {
    "o^indiccsimo": "quindicesimo",
    "dccimoscttimo": "decimosettimo",
    "dccimottavo": "decimottavo",
    "qyattordicesimo": "quattordicesimo",
    "qyinto": "quinto",
    "qyarto": "quarto",
    "qtiinto": "quinto",
    "ventesìmoteizo": "ventesimoterzo",
    # Compound forms that appear garbled
    "decimoqyinto": "decimoquinto",
    "ventesimoqtiinto": "ventesimoquinto",
}

# Word-level OCR fixes for individual ordinal words
WORD_FIXES = {
    "qyinto": "quinto",
    "qyarto": "quarto",
    "qtiinto": "quinto",
    "qyattordicesimo": "quattordicesimo",
}

# Compound ordinals that appear as multiple words
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


def build_chapter_id_map(italian_md_path: Path) -> dict[str, str]:
    """Build a mapping from short IDs (p1_ch01) to long IDs (p1_capitolo_primo).

    Returns a dict that maps both formats to the canonical long ID,
    so either can be used as input.
    """
    from translate import parse_italian_markdown

    text = italian_md_path.read_text(encoding="utf-8")
    chapters = parse_italian_markdown(text)
    content = [ch for ch in chapters if not ch.get("is_structural")]

    mapping: dict[str, str] = {}
    current_part = None
    part_idx = 0

    for ch in content:
        long_id = ch["id"]
        if long_id.startswith("p1_") and current_part != "p1":
            current_part = "p1"
            part_idx = 0
        elif long_id.startswith("p2_") and current_part != "p2":
            current_part = "p2"
            part_idx = 0
        elif long_id == "prefazione":
            mapping["prefazione"] = "prefazione"
            continue

        part_idx += 1
        short_id = f"{current_part}_ch{part_idx:02d}"
        mapping[short_id] = long_id
        mapping[long_id] = long_id  # long form maps to itself

    return mapping


def resolve_chapter_ids(raw_ids: list[str], italian_md_path: Path) -> list[str]:
    """Resolve a list of chapter IDs, accepting either short or long format.

    Accepts: p1_ch01, p1_capitolo_primo, prefazione, etc.
    Returns: list of canonical long-form IDs.
    """
    id_map = build_chapter_id_map(italian_md_path)
    resolved = []
    for raw in raw_ids:
        if raw in id_map:
            resolved.append(id_map[raw])
        else:
            print(f"  Warning: unknown chapter ID '{raw}', passing through as-is")
            resolved.append(raw)
    return resolved


def strip_accents(text: str) -> str:
    """Remove accents for comparison purposes."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_for_comparison(text: str) -> str:
    """Normalize text for fuzzy comparison: lowercase, strip accents, remove non-alpha."""
    text = strip_accents(text.lower())
    text = re.sub(r"[^a-z]", "", text)
    return text


def strip_boilerplate(text: str) -> str:
    """Remove metadata/boilerplate: keep only content between PREFAZIONE and INDICE."""
    lines = text.split("\n")

    # Find PREFAZIONE — book content starts there
    start = 0
    for i, line in enumerate(lines):
        if re.match(r"\s*PREFAZIONE\s*$", line):
            start = i
            break

    # Find INDICE near the end — content stops before it
    end = len(lines)
    for i in range(len(lines) - 1, -1, -1):
        if re.match(r"\s*INDICE\s*$", lines[i]):
            end = i
            break

    return "\n".join(lines[start:end])


# Backwards-compatible aliases
strip_boilerplate_copy1 = strip_boilerplate
strip_boilerplate_copy2 = strip_boilerplate


def _parse_chapter_number(words: list[str]) -> int | None:
    """Parse chapter number from the words following 'Capitolo'."""
    if not words:
        return None

    # Join and normalize all remaining words
    joined = "".join(w.lower() for w in words)

    # Check OCR fixes first
    for garble, fix in ORDINAL_FIXES.items():
        if normalize_for_comparison(joined) == normalize_for_comparison(garble):
            joined = fix
            break

    # Try single-word ordinal
    normalized = normalize_for_comparison(joined)
    for ordinal, num in ORDINALS.items():
        if normalize_for_comparison(ordinal) == normalized:
            return num

    # Try two-word compound ordinal (with word-level OCR fix)
    if len(words) >= 2:
        w1 = normalize_for_comparison(words[0])
        w2_raw = words[1].lower().strip()
        # Apply word-level OCR fixes
        w2_fixed = WORD_FIXES.get(w2_raw, w2_raw)
        w2 = normalize_for_comparison(w2_fixed)
        for (o1, o2), num in COMPOUND_ORDINALS.items():
            if (normalize_for_comparison(o1) == w1 and
                    normalize_for_comparison(o2) == w2):
                return num

    # Try first word only (for cases like "Ventesimoquarto")
    w1_norm = normalize_for_comparison(words[0])
    for ordinal, num in ORDINALS.items():
        if normalize_for_comparison(ordinal) == w1_norm:
            return num

    return None


def _is_chapter_heading(line: str) -> tuple[int, str] | None:
    """Check if a line is a chapter heading. Returns (chapter_num, raw_title) or None."""
    # Match "Capitolo" with possible OCR garbles (Gtpitolo, etc.)
    stripped = re.sub(r"\s+", " ", line.strip())
    match = re.match(
        r"(?:[GC][a-z]*pitolo|Capitolo)\s+(.+)",
        stripped,
        re.IGNORECASE,
    )
    if not match:
        return None

    rest = match.group(1).strip()
    # Remove leading/trailing noise characters (^, digits, etc.)
    rest = re.sub(r"[^a-zA-ZàèìòùéÀÈÌÒÙÈ\s]", "", rest).strip()
    if not rest:
        return None

    words = rest.split()
    num = _parse_chapter_number(words)
    if num is not None:
        return (num, stripped)
    return None


def split_into_chapters(text: str) -> list[dict]:
    """Split stripped text into chapters.

    Returns list of dicts:
        {"id": "prefazione"|"p1_ch01"|"p2_ch01", "title": str, "part": 0|1|2, "text": str}
    """
    lines = text.split("\n")
    chapters = []
    current_part = 1  # Start in Part 1
    current_chapter = None
    current_lines = []

    # Track if we've seen PREFAZIONE
    in_prefazione = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Detect PREFAZIONE
        if re.match(r"\s*PREFAZIONE\s*$", stripped) and not in_prefazione:
            in_prefazione = True
            current_chapter = {"id": "prefazione", "title": "PREFAZIONE", "part": 0}
            current_lines = []
            continue

        # Detect PARTE SECONDA
        if re.match(r"\s*PARTE\s+SECONDA\s*$", stripped):
            current_part = 2
            continue

        # Detect FINE DELLA PRIMA PARTE
        if re.match(r"\s*FINE\s+DELLA\s+PRIMA\s+PARTE\s*$", stripped):
            continue

        # Detect PER LA LIBERTA heading (appears between prefazione and ch1)
        if re.match(r"\s*PER\s+LA\s+LIBERT[AÀ]!?\s*$", stripped):
            continue

        # Detect chapter heading
        ch_info = _is_chapter_heading(stripped)
        if ch_info is not None:
            ch_num, raw_title = ch_info

            # Save previous chapter
            if current_chapter is not None:
                current_chapter["text"] = "\n".join(current_lines)
                chapters.append(current_chapter)

            ch_id = f"p{current_part}_ch{ch_num:02d}"
            current_chapter = {
                "id": ch_id,
                "title": raw_title,
                "part": current_part,
                "text": "",
            }
            current_lines = []
            continue

        current_lines.append(line)

    # Save last chapter
    if current_chapter is not None:
        current_chapter["text"] = "\n".join(current_lines)
        chapters.append(current_chapter)

    return chapters


def rejoin_lines(text: str) -> str:
    """Rejoin short OCR lines into paragraphs. Blank lines separate paragraphs."""
    paragraphs = []
    current = []

    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            if current:
                paragraphs.append(" ".join(current))
                current = []
        else:
            # Handle hyphenated line breaks
            if current and current[-1].endswith("-"):
                # Only rejoin if next line starts lowercase (broken word).
                # Preserves genuine hyphens at line end (e.g., compound words).
                if stripped[0].islower():
                    current[-1] = current[-1][:-1] + stripped
                else:
                    current.append(stripped)
            else:
                current.append(stripped)

    if current:
        paragraphs.append(" ".join(current))

    return "\n\n".join(paragraphs)


def collapse_spaces(text: str) -> str:
    """Collapse multiple spaces to single space within lines."""
    return re.sub(r"  +", " ", text)


def atomic_write_json(path: Path, data: dict | list) -> None:
    """Write JSON atomically: write to temp file, then rename."""
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
    except BaseException:
        os.unlink(tmp_path)
        raise


def retry_api_call(fn, *args, max_attempts: int = 3, retryable_exceptions: tuple | None = None, **kwargs):
    """Retry an API call with exponential backoff on transient errors.

    If retryable_exceptions is provided, those exception types are caught.
    Otherwise defaults to the standard Anthropic transient error set.
    """
    if retryable_exceptions is None:
        import anthropic

        retryable_exceptions = (
            anthropic.RateLimitError,
            anthropic.InternalServerError,
            anthropic.APITimeoutError,
            anthropic.APIConnectionError,
        )
    delays = [2, 4, 8]

    for attempt in range(max_attempts):
        try:
            return fn(*args, **kwargs)
        except retryable_exceptions as e:
            if attempt == max_attempts - 1:
                raise
            delay = delays[attempt]
            print(f"    Retrying in {delay}s ({type(e).__name__}: {e})")
            time.sleep(delay)
