"""Adjudicate unresolved hyphenated tokens using the Zingarelli 1922 dictionary.

Reads review_flags.json (sidecar from cleanup step) and classifies each
token by looking up its parts in the period-appropriate Italian dictionary.

Classifications:
  - compound:  both parts are real Italian words → keep hyphen
  - ner:       proper noun / named entity → keep hyphen
  - noise:     OCR garbage (no alphabetic content) → flag for removal
  - corrected: broken word with a plausible correction found → suggest fix
  - unknown:   needs LLM adjudication with dictionary context
"""

import json
import re
from pathlib import Path


DICT_DIR = Path(__file__).parent / "assets" / "dictionary" / "zingarelli_1922"

# Reuse the OCR boundary substitution logic from cleanup
BOUNDARY_SUBS: dict[str, list[str]] = {"i": ["r", "e"]}

# Cache for loaded dictionary chunks (module-level, shared across calls)
_chunks_cache: dict[str, str] = {}

_ACCENT_MAP = str.maketrans(
    "àáâèéêìíîòóôùúû", "aaaeeeiiiooouu" + "u"
)


def _strip_accents(text: str) -> str:
    return text.translate(_ACCENT_MAP)


def _load_chunk(letter: str) -> str:
    """Load the Zingarelli chunk for a given letter."""
    path = DICT_DIR / f"{letter.lower()}.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _search_chunk(word: str, chunk_text: str) -> list[str]:
    """Search for a word in a dictionary chunk using word-boundary matching.

    Returns lines where the word appears as a standalone token (not as a
    substring of another word). This prevents 'fl' matching inside 'ffle'.
    """
    if not word or not chunk_text or len(word) < 3:
        return []
    # Word boundary match — the word must be bordered by non-alpha chars
    pattern = re.compile(
        r"(?<![a-zA-ZÀ-ÿ])" + re.escape(word) + r"(?![a-zA-ZÀ-ÿ])",
        re.IGNORECASE,
    )
    matches = []
    for line in chunk_text.split("\n"):
        if pattern.search(line):
            matches.append(line.strip())
            if len(matches) >= 5:
                break
    return matches


def _word_in_zingarelli(word: str, chunks_cache: dict[str, str]) -> tuple[bool, list[str]]:
    """Check if a word appears in the Zingarelli dictionary as a standalone entry.

    Returns (found, matching_lines). Words shorter than 3 chars are rejected
    to avoid false matches on OCR noise fragments.
    """
    if not word or len(word) < 3:
        return False, []

    base = word[0].lower()
    base = _strip_accents(base)

    if base not in chunks_cache:
        chunks_cache[base] = _load_chunk(base)

    chunk = chunks_cache[base]
    matches = _search_chunk(word, chunk)

    # Also try accent-stripped form
    if not matches:
        stripped = _strip_accents(word)
        if stripped != word:
            matches = _search_chunk(stripped, chunk)

    return bool(matches), matches


def _is_noise(token: str) -> bool:
    """Check if a token is OCR noise (very few alphabetic characters)."""
    alpha = sum(1 for c in token if c.isalpha())
    return alpha < 3 or (len(token) > 3 and alpha / len(token) < 0.5)


def _try_corrections(left: str, right: str, chunks_cache: dict[str, str]) -> str | None:
    """Try to find the intended word using the same passes as dehyphenate_token,
    but validated against Zingarelli instead of the frequency dictionary."""
    # Pass 1: simple join
    joined = left + right
    found, _ = _word_in_zingarelli(joined, chunks_cache)
    if found:
        return joined

    # Pass 2: i→r / i→e substitution at end of left
    for pos in range(max(0, len(left) - 2), len(left)):
        ch = left[pos].lower()
        if ch in BOUNDARY_SUBS:
            for repl in BOUNDARY_SUBS[ch]:
                candidate = left[:pos] + repl + left[pos + 1:] + right
                found, _ = _word_in_zingarelli(candidate, chunks_cache)
                if found:
                    return candidate

    # Pass 3: substitution at start of right
    for pos in range(min(2, len(right))):
        ch = right[pos].lower()
        if ch in BOUNDARY_SUBS:
            for repl in BOUNDARY_SUBS[ch]:
                candidate = left + right[:pos] + repl + right[pos + 1:]
                found, _ = _word_in_zingarelli(candidate, chunks_cache)
                if found:
                    return candidate

    # Pass 4a: drop boundary 'i'
    if len(left) > 1 and left[-1].lower() == "i":
        candidate = left[:-1] + right
        found, _ = _word_in_zingarelli(candidate, chunks_cache)
        if found:
            return candidate

    # Pass 4b: drop duplicated char at boundary
    if len(left) > 1 and len(right) > 1 and left[-1].lower() == right[0].lower():
        candidate = left[:-1] + right
        found, _ = _word_in_zingarelli(candidate, chunks_cache)
        if found:
            return candidate

    return None


def zingarelli_lookup(word: str, context_lines: int = 3) -> str | None:
    """Look up a word in the Zingarelli 1922 dictionary.

    Returns a string with matching dictionary lines (up to `context_lines`),
    or None if not found. Usable by LLM cleanup to get period-appropriate
    dictionary context for OCR correction decisions.
    """
    found, matches = _word_in_zingarelli(word, _chunks_cache)
    if not found:
        # Try accent-stripped
        stripped = _strip_accents(word)
        if stripped != word:
            found, matches = _word_in_zingarelli(stripped, _chunks_cache)
    if matches:
        return "\n".join(matches[:context_lines])
    return None


def zingarelli_context_for_flags(flags: list[dict]) -> str:
    """Build Zingarelli dictionary context for a list of flagged tokens.

    Returns a formatted string suitable for inclusion in an LLM prompt,
    showing dictionary evidence for each flagged token's parts.
    """
    if not flags:
        return ""

    sections = []
    for item in flags:
        token = item["token"]
        left = item["left"]
        right = item["right"]

        parts = []
        for part in [left, right]:
            context = zingarelli_lookup(part)
            if context:
                parts.append(f"  '{part}': {context.split(chr(10))[0][:120]}")
            else:
                parts.append(f"  '{part}': not found in Zingarelli 1922")

        sections.append(f"Token: {token}\n" + "\n".join(parts))

    return (
        "=== Zingarelli 1922 Dictionary Reference ===\n"
        + "\n\n".join(sections)
        + "\n=== End Dictionary Reference ===\n"
    )


def adjudicate(data_dir: Path) -> dict:
    """Process dehyphenation flags and classify each token.

    Returns a dict mapping chapter_id → list of adjudicated entries.
    """
    flags_path = data_dir / "review_flags.json"
    if not flags_path.exists():
        print("  No review flags found")
        return {}

    flags = json.loads(flags_path.read_text(encoding="utf-8"))
    chunks_cache: dict[str, str] = {}
    results: dict[str, list[dict]] = {}

    stats = {"compound": 0, "ner": 0, "noise": 0, "corrected": 0, "unknown": 0}

    for chapter_id, items in flags.items():
        chapter_results = []

        for item in items:
            token = item["token"]
            left = item["left"]
            right = item["right"]
            original_reason = item["reason"]

            entry = {**item}

            # Step 1: noise detection
            if _is_noise(token):
                entry["resolution"] = "noise"
                entry["detail"] = "OCR garbage — too few alphabetic characters"
                stats["noise"] += 1
                chapter_results.append(entry)
                continue

            # Step 2: NER — both parts capitalized, neither in dictionary
            if original_reason == "ner_candidate":
                left_found, _ = _word_in_zingarelli(left, chunks_cache)
                right_found, _ = _word_in_zingarelli(right, chunks_cache)
                if not left_found and not right_found:
                    entry["resolution"] = "ner"
                    entry["detail"] = "Proper noun — neither part in Zingarelli"
                    stats["ner"] += 1
                    chapter_results.append(entry)
                    continue
                # If one or both parts ARE dictionary words, still likely NER
                # (e.g. Lombardo is also an adjective) — keep as NER if capitalized
                if left[0].isupper() and right[0].isupper():
                    entry["resolution"] = "ner"
                    zingarelli_note = []
                    if left_found:
                        zingarelli_note.append(f"'{left}' is also a dictionary word")
                    if right_found:
                        zingarelli_note.append(f"'{right}' is also a dictionary word")
                    entry["detail"] = f"Proper noun (both caps). {'; '.join(zingarelli_note)}"
                    stats["ner"] += 1
                    chapter_results.append(entry)
                    continue

            # Step 3: compound detection — both parts are real words.
            # Require ≥4 chars per part AND ≥2 matches each to avoid false
            # hits on OCR noise or incidental name references in Zingarelli.
            left_found, left_matches = _word_in_zingarelli(left, chunks_cache)
            right_found, right_matches = _word_in_zingarelli(right, chunks_cache)

            # Short words (≤5 chars) need ≥2 hits to avoid noise;
            # longer words (≥6 chars) are trusted with a single match.
            def _confident(word, matches):
                return len(matches) >= (2 if len(word) <= 5 else 1)

            is_compound = (
                left_found and right_found
                and len(left) >= 4 and len(right) >= 4
                and _confident(left, left_matches)
                and _confident(right, right_matches)
            )
            if is_compound:
                entry["resolution"] = "compound"
                entry["detail"] = f"Both parts in Zingarelli ({len(left_matches)}+{len(right_matches)} hits)"
                stats["compound"] += 1
                chapter_results.append(entry)
                continue

            # Step 4: try correction passes (same as dehyphenation but against Zingarelli)
            correction = _try_corrections(left, right, chunks_cache)
            if correction:
                _, matches = _word_in_zingarelli(correction, chunks_cache)
                entry["resolution"] = "corrected"
                entry["suggestion"] = correction
                entry["detail"] = f"Zingarelli match: {matches[0][:80] if matches else correction}"
                stats["corrected"] += 1
                chapter_results.append(entry)
                continue

            # Step 5: check if one part is a real word (partial match)
            if left_found and not right_found:
                entry["resolution"] = "unknown"
                entry["detail"] = f"Left part '{left}' in Zingarelli; right '{right}' not found"
            elif right_found and not left_found:
                entry["resolution"] = "unknown"
                entry["detail"] = f"Right part '{right}' in Zingarelli; left '{left}' not found"
            else:
                entry["resolution"] = "unknown"
                entry["detail"] = "Neither part in Zingarelli"

            stats["unknown"] += 1
            chapter_results.append(entry)

        if chapter_results:
            results[chapter_id] = chapter_results

    # Print summary
    total = sum(stats.values())
    print(f"  Adjudication results ({total} tokens):")
    for classification, count in stats.items():
        if count:
            print(f"    {classification:12s}: {count}")

    return results


def main():
    base = Path(__file__).parent
    data_dir = base / "data"

    results = adjudicate(data_dir)

    # Write adjudicated results
    from utils import atomic_write_json
    out_path = data_dir / "adjudication_results.json"
    atomic_write_json(out_path, results)
    print(f"\n  Results: {out_path}")

    # Print details
    for chapter_id, items in results.items():
        for item in items:
            res = item["resolution"]
            token = item["token"]
            detail = item.get("detail", "")
            suggestion = item.get("suggestion", "")
            marker = {"compound": "✓", "ner": "◆", "noise": "✗", "corrected": "→", "unknown": "?"}
            icon = marker.get(res, " ")
            line = f"  {icon} {chapter_id:12s} {token:25s} [{res:10s}]"
            if suggestion:
                line += f"  → {suggestion}"
            elif detail:
                line += f"  {detail[:60]}"
            print(line)


if __name__ == "__main__":
    main()
