"""Step 2: Align and reconcile two or three OCR copies at paragraph and word level."""

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


# Page marker pattern from ocr.py: ⟨PAGE:N⟩
PAGE_MARKER_RE = re.compile(r"\u27e8PAGE:(\d+)\u27e9")


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

    # Reward "clean" words — all standard letters
    if re.match(r"^[a-zA-ZàèìòùéÀÈÌÒÙ]+[.,;:!?]*$", word):
        score += 2

    return score


def split_paragraphs(text: str) -> list[str]:
    """Split chapter text into paragraphs (blank-line separated, lines rejoined)."""
    rejoined = rejoin_lines(text)
    paras = [p.strip() for p in rejoined.split("\n\n") if p.strip()]
    return paras


def _is_near_duplicate(
    norm_text: str, included_norms: list[str], threshold: float = 75,
) -> bool:
    """Check if normalized text is a near-duplicate of any already-included paragraph.

    Uses rapidfuzz for better OCR-variant matching than difflib.SequenceMatcher,
    plus a concatenated-window check for paragraphs whose content spans multiple
    already-included paragraphs (e.g. when one OCR witness merges paragraphs that
    others keep separate).
    """
    from rapidfuzz import fuzz

    if not norm_text or len(norm_text) < 20:
        return True  # Too short to be meaningful — skip

    # Tier 1: individual paragraph comparison
    for inc in included_norms:
        if fuzz.ratio(norm_text, inc) > threshold:
            return True
        # Containment: is candidate mostly found within a single included paragraph?
        if len(norm_text) <= len(inc) and fuzz.partial_ratio(norm_text, inc) >= 90:
            return True

    # Tier 2: concatenated-window check for long candidates whose content
    # may be spread across multiple shorter included paragraphs
    if len(norm_text) >= 200 and len(included_norms) >= 3:
        window_size = max(3, len(norm_text) // 150)
        window_size = min(window_size, len(included_norms))
        for i in range(len(included_norms) - window_size + 1):
            window = "".join(included_norms[i : i + window_size])
            if len(window) < len(norm_text) // 2:
                continue
            if fuzz.partial_ratio(norm_text, window) >= 90:
                return True

    return False


def _split_merged_chapters(
    ch_map1: dict, ch_map2: dict, all_ids: list[str],
) -> None:
    """Split Copy2 chapters that absorbed adjacent chapters missing from Copy2.

    When Copy2 is missing a chapter that Copy1 has, the missing chapter's content
    was merged into the preceding Copy2 chapter. This function detects these cases
    and splits Copy2 using Copy1's chapter boundaries as a guide.
    """
    c1_ids = set(ch_map1.keys())
    c2_ids = set(ch_map2.keys())
    missing_from_c2 = c1_ids - c2_ids

    if not missing_from_c2:
        return

    for ch_id in sorted(missing_from_c2):
        c1_missing = ch_map1.get(ch_id)
        if not c1_missing:
            continue

        # Find the preceding chapter that contains the merged content
        ch_num = int(ch_id.split("ch")[1])
        part = ch_id.split("_")[0]
        prev_id = f"{part}_ch{ch_num - 1:02d}"
        c2_host = ch_map2.get(prev_id)
        c1_prev = ch_map1.get(prev_id)

        if not c2_host or not c1_prev:
            continue

        # Only split if Copy2 chapter is significantly larger than Copy1's version
        if len(c2_host["text"]) < len(c1_prev["text"]) * 1.4:
            continue

        # Use Copy1's chapter length ratio to estimate the split point in Copy2
        # Copy1 prev chapter ends at ~len(c1_prev) chars; in Copy2 this maps to
        # approximately the same fraction of the merged text
        c1_prev_len = len(c1_prev["text"])
        c1_total = c1_prev_len + len(c1_missing["text"])
        split_fraction = c1_prev_len / c1_total
        approx_split = int(len(c2_host["text"]) * split_fraction)

        # Find the nearest paragraph break to the approximate split point
        text = c2_host["text"]
        # Search for a double-newline near the split point
        best_break = approx_split
        for offset in range(0, min(2000, len(text) - approx_split)):
            for pos in [approx_split + offset, approx_split - offset]:
                if 0 < pos < len(text) - 1 and text[pos:pos+2] == "\n\n":
                    best_break = pos
                    break
            else:
                continue
            break

        # Split the text
        host_text = text[:best_break].rstrip()
        split_text = text[best_break:].lstrip()

        if not split_text:
            continue

        # Update the host chapter
        c2_host["text"] = host_text

        # Create the missing chapter in Copy2
        ch_map2[ch_id] = {
            "id": ch_id,
            "title": c1_missing["title"],
            "part": c1_missing["part"],
            "text": split_text,
        }
        print(f"    Split {prev_id} in Copy2: {prev_id}={len(host_text):,} + {ch_id}={len(split_text):,} chars")


def align_paragraphs(
    paras1: list[str], paras2: list[str]
) -> list[tuple[str | None, str | None]]:
    """Align paragraphs from two copies using SequenceMatcher opcodes."""
    norm1 = [normalize_for_comparison(p) for p in paras1]
    norm2 = [normalize_for_comparison(p) for p in paras2]

    aligned = []

    for tag, i1, i2, j1, j2 in SequenceMatcher(None, norm1, norm2).get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                aligned.append((paras1[i1 + k], paras2[j1 + k]))
        elif tag == "replace":
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


def align_paragraphs_3way(
    paras1: list[str], paras2: list[str], paras3: list[str]
) -> list[tuple[str | None, str | None, str | None]]:
    """Align paragraphs from three copies using Copy 1 as anchor.

    Aligns Copy 2 and Copy 3 independently against Copy 1,
    then merges into triples.
    """
    norm1 = [normalize_for_comparison(p) for p in paras1]
    norm2 = [normalize_for_comparison(p) for p in paras2]
    norm3 = [normalize_for_comparison(p) for p in paras3]

    # Build index maps: copy1_idx → copy2_idx, copy1_idx → copy3_idx
    def _build_map(norm_a, norm_b, paras_b):
        """Map indices from norm_a to norm_b."""
        idx_map = {}
        for tag, i1, i2, j1, j2 in SequenceMatcher(None, norm_a, norm_b).get_opcodes():
            if tag == "equal":
                for k in range(i2 - i1):
                    idx_map[i1 + k] = j1 + k
            elif tag == "replace":
                len1 = i2 - i1
                len2 = j2 - j1
                for k in range(min(len1, len2)):
                    idx_map[i1 + k] = j1 + k
        return idx_map

    map_1_to_2 = _build_map(norm1, norm2, paras2)
    map_1_to_3 = _build_map(norm1, norm3, paras3)

    triples = []
    used_2 = set()
    used_3 = set()

    for i, p1 in enumerate(paras1):
        j = map_1_to_2.get(i)
        k = map_1_to_3.get(i)
        p2 = paras2[j] if j is not None else None
        p3 = paras3[k] if k is not None else None
        if j is not None:
            used_2.add(j)
        if k is not None:
            used_3.add(k)
        triples.append((p1, p2, p3))

    # Add unmatched paragraphs only if they aren't near-duplicates of included text
    included_norms = []
    for (p1, p2, p3) in triples:
        for p in (p1, p2, p3):
            if p is not None:
                included_norms.append(normalize_for_comparison(p))

    for j, p2 in enumerate(paras2):
        if j not in used_2:
            norm_p2 = normalize_for_comparison(p2)
            if not _is_near_duplicate(norm_p2, included_norms):
                triples.append((None, p2, None))
                included_norms.append(norm_p2)
    for k, p3 in enumerate(paras3):
        if k not in used_3:
            norm_p3 = normalize_for_comparison(p3)
            if not _is_near_duplicate(norm_p3, included_norms):
                triples.append((None, None, p3))
                included_norms.append(norm_p3)

    return triples


def reconcile_words(
    text1: str, text2: str, chapter_id: str, para_idx: int
) -> tuple[str, list[dict]]:
    """Reconcile two versions of the same paragraph at word level.

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
                                "resolution_method": "score_heuristic",
                            }
                        )
        elif tag == "insert":
            result.extend(words2[j1:j2])
        elif tag == "delete":
            result.extend(words1[i1:i2])

    return " ".join(result), flagged


def reconcile_words_3way(
    text1: str, text2: str, text3: str, chapter_id: str, para_idx: int
) -> tuple[str, list[dict]]:
    """Reconcile three versions of the same paragraph at word level.

    Uses majority voting: when 2 of 3 witnesses agree, auto-accept.
    When all 3 differ, fall back to score_word() and flag for triage.

    Returns (best_text, flagged_items).
    """
    words1 = text1.split()
    words2 = text2.split()
    words3 = text3.split()

    # Align all three against words1 as anchor
    # First: align words2 to words1
    align_1_2 = {}
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, words1, words2).get_opcodes():
        if tag == "equal" or tag == "replace":
            len1 = i2 - i1
            len2 = j2 - j1
            for k in range(min(len1, len2)):
                align_1_2[i1 + k] = j1 + k

    # Second: align words3 to words1
    align_1_3 = {}
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, words1, words3).get_opcodes():
        if tag == "equal" or tag == "replace":
            len1 = i2 - i1
            len2 = j2 - j1
            for k in range(min(len1, len2)):
                align_1_3[i1 + k] = j1 + k

    result = []
    flagged = []

    for i, w1 in enumerate(words1):
        j = align_1_2.get(i)
        k = align_1_3.get(i)
        w2 = words2[j] if j is not None else None
        w3 = words3[k] if k is not None else None

        # Normalize for comparison
        n1 = normalize_for_comparison(w1)
        n2 = normalize_for_comparison(w2) if w2 else None
        n3 = normalize_for_comparison(w3) if w3 else None

        # Check for majority agreement
        if n2 is not None and n3 is not None:
            if n1 == n2 and n1 == n3:
                # All agree
                result.append(w1)
                continue
            elif n1 == n2:
                # Copy 1 and 2 agree
                result.append(w1)
                continue
            elif n1 == n3:
                # Copy 1 and 3 agree
                result.append(w1)
                continue
            elif n2 == n3:
                # Copy 2 and 3 agree — prefer w2 (different physical copy)
                result.append(w2)
                continue
            else:
                # All three differ — use scoring, flag for triage
                s1 = score_word(w1)
                s2 = score_word(w2)
                s3 = score_word(w3)

                best_score = max(s1, s2, s3)
                if s1 == best_score:
                    chosen = w1
                elif s2 == best_score:
                    chosen = w2
                else:
                    chosen = w3

                result.append(chosen)

                # Build context (5 words before/after)
                ctx_start = max(0, i - 5)
                ctx_end = min(len(words1), i + 6)
                context = " ".join(words1[ctx_start:ctx_end])

                flagged.append({
                    "chapter": chapter_id,
                    "paragraph": para_idx,
                    "word_copy1": w1,
                    "word_copy2": w2,
                    "word_copy3": w3,
                    "score1": s1,
                    "score2": s2,
                    "score3": s3,
                    "chosen": chosen,
                    "resolution_method": "all_differ",
                    "context": context,
                })
                continue

        # Fallback: only 2 copies available for this word
        if w2 is not None and n1 != n2:
            s1 = score_word(w1)
            s2 = score_word(w2)
            chosen = w1 if s1 >= s2 else w2
            result.append(chosen)

            if abs(s1 - s2) <= 2:
                flagged.append({
                    "chapter": chapter_id,
                    "paragraph": para_idx,
                    "word_copy1": w1,
                    "word_copy2": w2,
                    "word_copy3": w3,
                    "score1": s1,
                    "score2": s2,
                    "score3": score_word(w3) if w3 else None,
                    "chosen": chosen,
                    "resolution_method": "score_heuristic",
                    "context": "",
                })
        elif w3 is not None and n1 != n3:
            s1 = score_word(w1)
            s3 = score_word(w3)
            chosen = w1 if s1 >= s3 else w3
            result.append(chosen)
        else:
            result.append(w1)

    # Handle words in Copy 2/3 that weren't aligned to Copy 1
    # (insertions) — defer to 2-way logic between copies
    # This is a simplification; most content aligns to Copy 1.

    return " ".join(result), flagged


def _strip_page_markers(text: str) -> tuple[str, dict[int, int]]:
    """Remove ⟨PAGE:N⟩ markers from text and build char_offset → page_num map.

    Returns (clean_text, {char_offset_in_clean: page_num}).
    """
    page_breaks = {}
    clean_parts = []
    clean_pos = 0

    for line in text.split("\n"):
        m = PAGE_MARKER_RE.match(line.strip())
        if m:
            page_breaks[clean_pos] = int(m.group(1))
        else:
            clean_parts.append(line)
            clean_pos += len(line) + 1  # +1 for newline

    return "\n".join(clean_parts), page_breaks


def _find_page_for_paragraph(para_start: int, page_breaks: dict[int, int]) -> list[int]:
    """Find which page(s) a paragraph falls on given character offsets."""
    if not page_breaks:
        return []
    # Find the page marker just before or at para_start
    pages = []
    sorted_offsets = sorted(page_breaks.keys())
    current_page = None
    for offset in sorted_offsets:
        if offset <= para_start:
            current_page = page_breaks[offset]
        else:
            break
    if current_page is not None:
        pages.append(current_page)
    return pages


def reconcile(data_dir: Path, chapters: list[str] | None = None) -> None:
    """Main reconciliation: align chapters, paragraphs, and words (2-way or 3-way).

    Args:
        data_dir: Path to data directory containing copy*_raw.txt files.
        chapters: Optional list of chapter IDs to reconcile (e.g. ["p1_ch01", "p1_ch02"]).
            When specified, only these chapters are re-reconciled and the rest
            are preserved from the existing reconciled_chapters.json.
    """
    copy1_text = (data_dir / "copy1_raw.txt").read_text(encoding="utf-8")
    copy2_text = (data_dir / "copy2_raw.txt").read_text(encoding="utf-8")

    # Check for third copy (Gemini OCR): prefer Pro, fall back to Flash
    copy3_path = data_dir / "copy3_raw.txt"
    if not copy3_path.exists():
        copy3_path = data_dir / "copy3_flash.txt"
    has_copy3 = copy3_path.exists()
    copy3_text = ""
    copy3_page_breaks = {}

    if has_copy3:
        raw_copy3 = copy3_path.read_text(encoding="utf-8")
        copy3_text, copy3_page_breaks = _strip_page_markers(raw_copy3)
        print(f"  3-way mode: Copy 3 loaded ({len(copy3_text):,} chars, {len(copy3_page_breaks)} page markers)")
    else:
        print("  2-way mode: Copy 3 not found, falling back to 2-way reconciliation")

    stripped1 = strip_boilerplate_copy1(copy1_text)
    stripped2 = strip_boilerplate_copy2(copy2_text)

    stripped1 = collapse_spaces(stripped1)
    stripped2 = collapse_spaces(stripped2)

    chapters1 = split_into_chapters(stripped1)
    chapters2 = split_into_chapters(stripped2)

    ch_map1 = {ch["id"]: ch for ch in chapters1}
    ch_map2 = {ch["id"]: ch for ch in chapters2}

    # If we have Copy 3, split it into chapters too
    ch_map3 = {}
    if has_copy3:
        stripped3 = strip_boilerplate_copy1(copy3_text)  # Same scan as Copy 1
        stripped3 = collapse_spaces(stripped3)
        chapters3 = split_into_chapters(stripped3)
        ch_map3 = {ch["id"]: ch for ch in chapters3}
        print(f"  Copy 3 chapters: {len(chapters3)}")

    # Split Copy2 chapters that absorbed missing adjacent chapters
    _split_merged_chapters(ch_map1, ch_map2, sorted(ch_map1.keys()))

    all_ids = sorted(set(ch_map1.keys()) | set(ch_map2.keys()) | set(ch_map3.keys()))

    # When filtering by chapter, load existing results to preserve unmodified chapters
    existing_by_id = {}
    if chapters:
        out_path = data_dir / "reconciled_chapters.json"
        if out_path.exists():
            for ch in json.loads(out_path.read_text(encoding="utf-8")):
                existing_by_id[ch["id"]] = ch
        chapter_set = set(chapters)
        print(f"  Reconciling {len(chapter_set)} chapter(s): {', '.join(chapters)}")
    else:
        chapter_set = None

    reconciled_chapters = []
    all_flagged = []
    stats = {
        "shared": 0, "copy1_only": 0, "copy2_only": 0, "copy3_only": 0,
        "total_flagged": 0, "majority_resolved": 0, "all_differ": 0,
    }

    for ch_idx, ch_id in enumerate(all_ids):
        # If filtering and this chapter isn't targeted, use existing result
        if chapter_set and ch_id not in chapter_set:
            if ch_id in existing_by_id:
                reconciled_chapters.append(existing_by_id[ch_id])
            continue

        ch1 = ch_map1.get(ch_id)
        ch2 = ch_map2.get(ch_id)
        ch3 = ch_map3.get(ch_id)

        # Determine which copies are available
        available = [c for c in [ch1, ch2, ch3] if c is not None]
        if not available:
            continue

        # Use first available for metadata
        ref = available[0]
        print(f"    {ch_id}:", end="", flush=True)

        if ch1 and ch2 and ch3:
            # 3-way reconciliation
            stats["shared"] += 1
            paras1 = split_paragraphs(ch1["text"])
            paras2 = split_paragraphs(ch2["text"])
            paras3 = split_paragraphs(ch3["text"])

            aligned = align_paragraphs_3way(paras1, paras2, paras3)
            reconciled_paras = []
            reconciled_norms = []

            for para_idx, (p1, p2, p3) in enumerate(aligned):
                texts = [t for t in [p1, p2, p3] if t is not None]
                if len(texts) == 3:
                    merged, flagged = reconcile_words_3way(p1, p2, p3, ch_id, para_idx)
                    reconciled_paras.append(merged)
                    reconciled_norms.append(normalize_for_comparison(merged))
                    all_flagged.extend(flagged)
                    stats["all_differ"] += sum(1 for f in flagged if f["resolution_method"] == "all_differ")
                elif len(texts) == 2:
                    t1, t2 = texts[0], texts[1]
                    merged, flagged = reconcile_words(t1, t2, ch_id, para_idx)
                    reconciled_paras.append(merged)
                    reconciled_norms.append(normalize_for_comparison(merged))
                    all_flagged.extend(flagged)
                else:
                    # Single-source paragraph: skip if near-duplicate of already-included
                    norm = normalize_for_comparison(texts[0])
                    if not _is_near_duplicate(norm, reconciled_norms):
                        reconciled_paras.append(texts[0])
                        reconciled_norms.append(norm)

            n_aligned = len(aligned)
            n_kept = len(reconciled_paras)
            ch_chars = sum(len(p) for p in reconciled_paras)
            print(f" {n_aligned} aligned → {n_kept} kept ({ch_chars:,} chars)", flush=True)
            reconciled_chapters.append({
                "id": ch_id,
                "title": ch1["title"],
                "part": ch1["part"],
                "text": "\n\n".join(reconciled_paras),
            })

        elif ch1 and ch2:
            # 2-way reconciliation (original behavior)
            stats["shared"] += 1
            paras1 = split_paragraphs(ch1["text"])
            paras2 = split_paragraphs(ch2["text"])

            aligned = align_paragraphs(paras1, paras2)
            reconciled_paras = []
            reconciled_norms = []

            for para_idx, (p1, p2) in enumerate(aligned):
                if p1 is None and p2 is not None:
                    norm = normalize_for_comparison(p2)
                    if not _is_near_duplicate(norm, reconciled_norms):
                        reconciled_paras.append(p2)
                        reconciled_norms.append(norm)
                elif p2 is None and p1 is not None:
                    norm = normalize_for_comparison(p1)
                    if not _is_near_duplicate(norm, reconciled_norms):
                        reconciled_paras.append(p1)
                        reconciled_norms.append(norm)
                elif p1 is not None and p2 is not None:
                    merged, flagged = reconcile_words(p1, p2, ch_id, para_idx)
                    reconciled_paras.append(merged)
                    reconciled_norms.append(normalize_for_comparison(merged))
                    all_flagged.extend(flagged)

            n_aligned = len(aligned)
            n_kept = len(reconciled_paras)
            ch_chars = sum(len(p) for p in reconciled_paras)
            print(f" {n_aligned} aligned → {n_kept} kept ({ch_chars:,} chars)", flush=True)
            reconciled_chapters.append({
                "id": ch_id,
                "title": ch1["title"],
                "part": ch1["part"],
                "text": "\n\n".join(reconciled_paras),
            })

        else:
            # Single copy only
            key = "copy1_only" if ch1 else ("copy2_only" if ch2 else "copy3_only")
            stats[key] += 1
            paras = split_paragraphs(ref["text"])
            ch_chars = sum(len(p) for p in paras)
            print(f" single-source, {len(paras)} paras ({ch_chars:,} chars)", flush=True)
            reconciled_chapters.append({
                "id": ch_id,
                "title": ref["title"],
                "part": ref["part"],
                "text": "\n\n".join(paras),
            })

        # Save progress after each chapter so work isn't lost on crash
        chapters_path = data_dir / "reconciled_chapters.json"
        chapters_path.write_text(
            json.dumps(reconciled_chapters, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    stats["total_flagged"] = len(all_flagged)
    stats["majority_resolved"] = stats["total_flagged"] - stats["all_differ"]

    # Build page provenance from Copy 3 page markers
    if has_copy3 and copy3_page_breaks:
        # Prefer flash page map (finishes first), fall back to pro
        page_map_path = data_dir / "copy3_flash_page_map.json"
        if not page_map_path.exists():
            page_map_path = data_dir / "copy3_pro_page_map.json"
        if page_map_path.exists():
            page_map = json.loads(page_map_path.read_text(encoding="utf-8"))
            # Build chapter → page range mapping by accumulating char offsets
            # as we walk through stripped3 sequentially
            chapter_pages = {}
            search_pos = 0
            for ch in (chapters3 if ch_map3 else []):
                ch_id = ch["id"]
                if not ch["text"]:
                    continue
                # Search forward from last position to avoid false matches
                snippet = ch["text"][:80]
                ch_text_start = stripped3.find(snippet, search_pos)
                if ch_text_start < 0:
                    # Fallback: search from beginning
                    ch_text_start = stripped3.find(snippet)
                if ch_text_start >= 0:
                    ch_text_end = ch_text_start + len(ch["text"])
                    search_pos = ch_text_end
                    pages = set()
                    for entry in page_map:
                        # Skip low-content pages (cover, blanks, title page, catalog card)
                        if entry["char_end"] - entry["char_start"] < 500:
                            continue
                        if entry["char_start"] <= ch_text_end and entry["char_end"] >= ch_text_start:
                            pages.add(entry["page"])
                    if pages:
                        chapter_pages[ch_id] = sorted(pages)

            # Save chapter-to-page mapping
            chapter_pages_path = data_dir / "chapter_pages.json"
            chapter_pages_path.write_text(
                json.dumps(chapter_pages, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            print(f"  Chapter page mapping: {chapter_pages_path}")

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

    mode = "3-way" if has_copy3 else "2-way"
    print(f"  Reconciled {len(reconciled_chapters)} chapters ({mode})")
    print(
        f"  Shared: {stats['shared']}, Copy1 only: {stats['copy1_only']}, "
        f"Copy2 only: {stats['copy2_only']}"
        + (f", Copy3 only: {stats['copy3_only']}" if has_copy3 else "")
    )
    print(f"  Flagged word disagreements: {stats['total_flagged']}")
    if has_copy3:
        print(f"    Majority-resolved (2-of-3 agree): would have resolved many more")
        print(f"    All-3-differ (needs triage): {stats['all_differ']}")
    print(f"  Output: {reconciled_path}")
    print(f"  Flagged: {flagged_path}")


if __name__ == "__main__":
    reconcile(Path(__file__).parent / "data")
