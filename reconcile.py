"""Step 2: Align and reconcile two OCR copies at paragraph and word level."""

import json
import re
from difflib import SequenceMatcher
from pathlib import Path

from utils import (
    collapse_spaces,
    normalize_for_comparison,
    rejoin_lines,
    split_into_chapters,
    strip_boilerplate_copy1,
    strip_boilerplate_copy2,
)


def score_word(word: str) -> int:
    """Score a word for likely OCR correctness. Higher = more likely correct."""
    score = 0

    # Strong penalties
    if "*" in word:
        score -= 10
    if re.search(r"[(){}[\]|\\^~`]", word):
        score -= 8  # Brackets/parens inside a word = OCR noise

    # Reward proper Italian accents
    if re.search(r"[àèìòùéÀÈÌÒÙ]", word):
        score += 5

    # Penalize non-letter characters (excluding common punctuation at edges)
    inner = word.strip(".,;:!?\"'""''")
    if re.search(r"[^a-zA-ZàèìòùéÀÈÌÒÙ'\-]", inner):
        score -= 5

    # Penalize mid-word capitals (OCR artifact like "voM", "incoQseiamente")
    if len(word) > 1 and re.search(r"[A-Z]", word[1:]):
        score -= 4

    # Penalize doubled i's that likely represent 'u' OCR error (tranqiiilla)
    if "ii" in word.lower():
        score -= 3

    # Penalize common OCR confusion: lone 'm' or 'n' substituted
    # Words starting with 'im' where 'un' is expected, etc.
    # (Can't reliably detect without dictionary, so skip)

    # Reward "clean" words — all standard letters
    if re.match(r"^[a-zA-ZàèìòùéÀÈÌÒÙ]+[.,;:!?]*$", word):
        score += 2

    return score


def split_paragraphs(text: str) -> list[str]:
    """Split chapter text into paragraphs (blank-line separated, lines rejoined)."""
    rejoined = rejoin_lines(text)
    paras = [p.strip() for p in rejoined.split("\n\n") if p.strip()]
    return paras


def align_paragraphs(
    paras1: list[str], paras2: list[str]
) -> list[tuple[str | None, str | None]]:
    """Align paragraphs from two copies using rapidfuzz Levenshtein opcodes."""
    # Normalize for matching
    norm1 = [normalize_for_comparison(p) for p in paras1]
    norm2 = [normalize_for_comparison(p) for p in paras2]

    aligned = []

    for tag, i1, i2, j1, j2 in SequenceMatcher(None, norm1, norm2).get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                aligned.append((paras1[i1 + k], paras2[j1 + k]))
        elif tag == "replace":
            # Pair up as many as possible, leave extras unpaired
            len1 = i2 - i1
            len2 = j2 - j1
            for k in range(max(len1, len2)):
                p1 = paras1[i1 + k] if k < len1 else None
                p2 = paras2[j1 + k] if k < len2 else None
                aligned.append((p1, p2))
        elif tag == "insert":
            for k in range(j1, j2):
                aligned.append((None, paras2[k]))
        elif tag == "delete":
            for k in range(i1, i2):
                aligned.append((paras1[k], None))

    return aligned


def reconcile_words(
    text1: str, text2: str, chapter_id: str, para_idx: int
) -> tuple[str, list[dict]]:
    """Reconcile two versions of the same paragraph at word level.

    Uses whitespace-split tokenization (safe for apostrophe contractions)
    and rapidfuzz Levenshtein for alignment.
    Returns (best_text, flagged_items).
    """
    words1 = text1.split()
    words2 = text2.split()

    result = []
    flagged = []

    for tag, i1, i2, j1, j2 in SequenceMatcher(None, words1, words2).get_opcodes():
        if tag == "equal":
            result.extend(words1[i1:i2])
        elif tag == "replace":
            # Compare word by word where possible
            len1 = i2 - i1
            len2 = j2 - j1
            for k in range(max(len1, len2)):
                w1 = words1[i1 + k] if k < len1 else None
                w2 = words2[j1 + k] if k < len2 else None

                if w1 is None:
                    result.append(w2)
                elif w2 is None:
                    result.append(w1)
                else:
                    s1 = score_word(w1)
                    s2 = score_word(w2)
                    if s1 >= s2:
                        result.append(w1)
                    else:
                        result.append(w2)

                    # Flag if scores are close and words differ significantly
                    if (
                        abs(s1 - s2) <= 2
                        and normalize_for_comparison(w1)
                        != normalize_for_comparison(w2)
                    ):
                        flagged.append(
                            {
                                "chapter": chapter_id,
                                "paragraph": para_idx,
                                "word_copy1": w1,
                                "word_copy2": w2,
                                "score1": s1,
                                "score2": s2,
                                "chosen": w1 if s1 >= s2 else w2,
                            }
                        )
        elif tag == "insert":
            result.extend(words2[j1:j2])
        elif tag == "delete":
            result.extend(words1[i1:i2])

    return " ".join(result), flagged


def reconcile(data_dir: Path) -> None:
    """Main reconciliation: align chapters, paragraphs, and words."""
    copy1_text = (data_dir / "copy1_raw.txt").read_text(encoding="utf-8")
    copy2_text = (data_dir / "copy2_raw.txt").read_text(encoding="utf-8")

    stripped1 = strip_boilerplate_copy1(copy1_text)
    stripped2 = strip_boilerplate_copy2(copy2_text)

    # Collapse multi-spaces for cleaner processing
    stripped1 = collapse_spaces(stripped1)
    stripped2 = collapse_spaces(stripped2)

    chapters1 = split_into_chapters(stripped1)
    chapters2 = split_into_chapters(stripped2)

    ch_map1 = {ch["id"]: ch for ch in chapters1}
    ch_map2 = {ch["id"]: ch for ch in chapters2}

    all_ids = sorted(set(ch_map1.keys()) | set(ch_map2.keys()))

    reconciled_chapters = []
    all_flagged = []
    stats = {"shared": 0, "copy1_only": 0, "copy2_only": 0, "total_flagged": 0}

    for ch_id in all_ids:
        ch1 = ch_map1.get(ch_id)
        ch2 = ch_map2.get(ch_id)

        if ch1 and ch2:
            stats["shared"] += 1
            # Both copies have this chapter — reconcile
            paras1 = split_paragraphs(ch1["text"])
            paras2 = split_paragraphs(ch2["text"])

            aligned = align_paragraphs(paras1, paras2)
            reconciled_paras = []

            for para_idx, (p1, p2) in enumerate(aligned):
                if p1 is None and p2 is not None:
                    reconciled_paras.append(p2)
                elif p2 is None and p1 is not None:
                    reconciled_paras.append(p1)
                elif p1 is not None and p2 is not None:
                    merged, flagged = reconcile_words(p1, p2, ch_id, para_idx)
                    reconciled_paras.append(merged)
                    all_flagged.extend(flagged)

            reconciled_chapters.append(
                {
                    "id": ch_id,
                    "title": ch1["title"],
                    "part": ch1["part"],
                    "text": "\n\n".join(reconciled_paras),
                }
            )

        elif ch1:
            stats["copy1_only"] += 1
            paras = split_paragraphs(ch1["text"])
            reconciled_chapters.append(
                {
                    "id": ch_id,
                    "title": ch1["title"],
                    "part": ch1["part"],
                    "text": "\n\n".join(paras),
                }
            )

        elif ch2:
            stats["copy2_only"] += 1
            paras = split_paragraphs(ch2["text"])
            reconciled_chapters.append(
                {
                    "id": ch_id,
                    "title": ch2["title"],
                    "part": ch2["part"],
                    "text": "\n\n".join(paras),
                }
            )

    stats["total_flagged"] = len(all_flagged)

    # Write reconciled text
    output_lines = []
    for ch in reconciled_chapters:
        output_lines.append(f"=== {ch['id']} | {ch['title']} ===")
        output_lines.append(ch["text"])
        output_lines.append("")

    reconciled_path = data_dir / "reconciled_raw.txt"
    reconciled_path.write_text("\n".join(output_lines), encoding="utf-8")

    # Write flagged segments
    flagged_path = data_dir / "flagged_segments.json"
    flagged_path.write_text(
        json.dumps(all_flagged, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Also save structured chapters as JSON for cleanup step
    chapters_path = data_dir / "reconciled_chapters.json"
    chapters_path.write_text(
        json.dumps(reconciled_chapters, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"  Reconciled {len(reconciled_chapters)} chapters")
    print(
        f"  Shared: {stats['shared']}, Copy1 only: {stats['copy1_only']}, Copy2 only: {stats['copy2_only']}"
    )
    print(f"  Flagged word disagreements: {stats['total_flagged']}")
    print(f"  Output: {reconciled_path}")
    print(f"  Flagged: {flagged_path}")


if __name__ == "__main__":
    reconcile(Path(__file__).parent / "data")
