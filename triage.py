"""Step 3a: LLM triage and resolution of flagged OCR disagreements.

Adapted from Athanor's 01e_llm_review.py + 01f_resolve.py for Italian OCR.
Processes items where majority voting couldn't resolve (all_differ + close-score).
"""

import json
import os
import time
from difflib import SequenceMatcher
from pathlib import Path


# Categories for Italian OCR disagreements
CATEGORIES = [
    "ocr_confusion",        # single-char swap: e/c, ii/u, m/rn
    "ocr_corruption",       # multi-char garble
    "punctuation_artifact",  # extra/missing punctuation
    "alignment_drift",      # text displaced between witnesses
    "missing_text",         # witness missing content
    "archaic_spelling",     # 1913 Italian variant, not an error
    "unknown",
]

TRIAGE_TOOL = {
    "name": "classify_disagreement",
    "description": (
        "Classify an OCR disagreement between witnesses and propose the correct reading."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "enum": CATEGORIES,
                "description": "The type of OCR disagreement.",
            },
            "proposed_reading": {
                "type": "string",
                "description": "The correct reading of the word. May be from any witness or a correction.",
            },
            "confidence": {
                "type": "string",
                "enum": ["high", "medium", "low"],
            },
            "reasoning": {
                "type": "string",
                "description": "One-sentence explanation of the classification.",
            },
            "needs_human": {
                "type": "boolean",
                "description": "True if this item needs human review.",
            },
        },
        "required": ["category", "proposed_reading", "confidence", "reasoning", "needs_human"],
    },
}

TRIAGE_SYSTEM = (
    "You are an expert in 19th/early 20th century Italian literature and OCR correction. "
    "You are triaging OCR disagreements from a digitized 1913 Italian book titled "
    "'Per la libertà!' by Cesare Crespi.\n\n"
    "Three OCR witnesses exist:\n"
    "- Copy 1: Library of Congress scan, Tesseract OCR\n"
    "- Copy 2: Google/Harvard scan, different OCR engine\n"
    "- Copy 3: Library of Congress scan, Gemini Vision OCR\n\n"
    "Common Italian OCR confusion patterns:\n"
    "- 'e' ↔ 'c' (eentro→centro, eome→come, cbe→che)\n"
    "- 'ii' → 'u' (piìi→più, tranqiiillo→tranquillo)\n"
    "- 'm' ↔ 'rn' (carne↔came)\n"
    "- Mid-word capitals from scan artifacts (incoQsciamente)\n"
    "- Missing/extra accents (pàtria vs patria — both valid in 1913 Italian)\n\n"
    "Rules:\n"
    "- Set needs_human=false ONLY when: category is clearly ocr_confusion or "
    "punctuation_artifact, one witness has the obviously correct reading, "
    "and confidence is 'high'\n"
    "- For archaic_spelling: the 1913 text may use accento facoltativo "
    "(pàtria, prìncipi, sècolo) — these are NOT errors\n"
    "- When in doubt, set needs_human=true"
)


def _is_plausible_correction(original: str, correction: str) -> bool:
    """Check if a correction is plausible (not alignment drift)."""
    if not original or not correction:
        return False
    # Character-level similarity must be >= 0.4
    ratio = SequenceMatcher(None, original.lower(), correction.lower()).ratio()
    return ratio >= 0.4


def triage_items(
    data_dir: Path,
    api_key: str | None = None,
    batch_size: int = 5,
) -> None:
    """LLM triage of flagged OCR disagreements.

    Processes items from flagged_segments.json, categorizes them,
    and resolves what it can automatically.
    """
    import anthropic

    from utils import retry_api_call

    flagged_path = data_dir / "flagged_segments.json"
    if not flagged_path.exists():
        print("  No flagged segments found — run reconcile first")
        return

    all_items = json.loads(flagged_path.read_text(encoding="utf-8"))
    print(f"  Loaded {len(all_items)} flagged items")

    # Filter to items that need triage (all_differ or close-score)
    needs_triage = [
        item for item in all_items
        if item.get("resolution_method") in ("all_differ", "score_heuristic")
    ]
    print(f"  Items needing triage: {len(needs_triage)}")

    if not needs_triage:
        print("  Nothing to triage")
        return

    if not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("  Warning: No API key, skipping LLM triage")
            return

    client = anthropic.Anthropic(api_key=api_key, timeout=300.0)

    # Process in batches
    reviewed = []
    total = len(needs_triage)
    bar_width = 30

    for batch_start in range(0, total, batch_size):
        batch = needs_triage[batch_start:batch_start + batch_size]
        batch_end = min(batch_start + batch_size, total)

        filled = int(bar_width * (batch_end / total))
        bar = "\u2588" * filled + "\u2591" * (bar_width - filled)
        print(f"\r  [{bar}] {batch_end}/{total}", end="", flush=True)

        # Build prompt for this batch
        items_desc = []
        for i, item in enumerate(batch):
            desc = f"Item {i+1}:\n"
            desc += f"  Chapter: {item['chapter']}, Paragraph: {item['paragraph']}\n"
            desc += f"  Copy 1: \"{item.get('word_copy1', 'N/A')}\"\n"
            desc += f"  Copy 2: \"{item.get('word_copy2', 'N/A')}\"\n"
            if item.get("word_copy3"):
                desc += f"  Copy 3: \"{item['word_copy3']}\"\n"
            if item.get("context"):
                desc += f"  Context: ...{item['context']}...\n"
            desc += f"  Currently chosen: \"{item['chosen']}\"\n"
            items_desc.append(desc)

        user_msg = (
            f"Classify each of these {len(batch)} OCR disagreements. "
            f"Call the classify_disagreement tool once for each item.\n\n"
            + "\n".join(items_desc)
        )

        def _call():
            return client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                system=TRIAGE_SYSTEM,
                tools=[TRIAGE_TOOL],
                messages=[{"role": "user", "content": user_msg}],
            )

        try:
            response = retry_api_call(_call)

            # Extract tool use responses
            tool_results = [
                block.input for block in response.content
                if hasattr(block, "type") and block.type == "tool_use"
                and hasattr(block, "name") and block.name == "classify_disagreement"
            ]

            if len(tool_results) != len(batch):
                print(f"\n    WARNING: Got {len(tool_results)} results for {len(batch)} items in batch")

            # Match results back to items (may have fewer results than items)
            for i, item in enumerate(batch):
                result = tool_results[i] if i < len(tool_results) else None
                reviewed_item = {**item}
                if result:
                    reviewed_item["triage"] = result
                else:
                    reviewed_item["triage"] = {
                        "category": "unknown",
                        "proposed_reading": item["chosen"],
                        "confidence": "low",
                        "reasoning": "No LLM response for this item",
                        "needs_human": True,
                    }
                reviewed.append(reviewed_item)

        except Exception as e:
            print(f"\n    Triage error on batch {batch_start}: {e}")
            for item in batch:
                reviewed.append({
                    **item,
                    "triage": {
                        "category": "unknown",
                        "proposed_reading": item["chosen"],
                        "confidence": "low",
                        "reasoning": f"API error: {e}",
                        "needs_human": True,
                    },
                })

        time.sleep(1)  # Rate limiting

    print(f"\r  [{'█' * bar_width}] {total}/{total} done!{' ' * 20}")

    # === Resolution passes ===

    resolved = []
    stats = {"auto_accepted": 0, "needs_human": 0, "by_category": {}}

    for item in reviewed:
        triage = item["triage"]
        category = triage["category"]
        stats["by_category"][category] = stats["by_category"].get(category, 0) + 1

        # Pass 1: Auto-accept high-confidence non-human items
        if not triage["needs_human"] and triage["confidence"] in ("high", "medium"):
            proposed = triage["proposed_reading"]
            if _is_plausible_correction(item["chosen"], proposed):
                item["resolved"] = proposed
                item["resolution_source"] = "llm_triage"
                stats["auto_accepted"] += 1
            else:
                # LLM was confident but correction is implausible (e.g., alignment drift)
                item["resolved"] = item["chosen"]
                item["resolution_source"] = "plausibility_rejected"
                stats["needs_human"] += 1
        elif triage["needs_human"]:
            item["resolved"] = item["chosen"]
            item["resolution_source"] = "needs_human"
            stats["needs_human"] += 1
        else:
            # Low confidence, not flagged for human — keep current choice
            item["resolved"] = item["chosen"]
            item["resolution_source"] = "low_confidence"
            stats["needs_human"] += 1

        resolved.append(item)

    # Write triage results
    triage_path = data_dir / "triage_review.json"
    triage_path.write_text(
        json.dumps(reviewed, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    resolved_path = data_dir / "triage_resolved.json"
    resolved_path.write_text(
        json.dumps(resolved, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Apply resolutions back to reconciled chapters
    _apply_resolutions(data_dir, resolved)

    print(f"\n  Triage complete:")
    print(f"    Auto-accepted: {stats['auto_accepted']}")
    print(f"    Needs human review: {stats['needs_human']}")
    print(f"    By category: {json.dumps(stats['by_category'], indent=6)}")
    print(f"    Review: {triage_path}")
    print(f"    Resolved: {resolved_path}")


def _apply_resolutions(data_dir: Path, resolved_items: list[dict]) -> None:
    """Apply triage resolutions back to reconciled_chapters.json."""
    chapters_path = data_dir / "reconciled_chapters.json"
    if not chapters_path.exists():
        print("    reconciled_chapters.json not found — run reconcile first")
        return

    chapters = json.loads(chapters_path.read_text(encoding="utf-8"))

    # Group corrections by (chapter, paragraph) to handle duplicates safely.
    # Each correction tracks the original word and its replacement; we apply
    # only the first match per paragraph to avoid replacing the wrong instance.
    from collections import defaultdict

    per_para = defaultdict(list)
    for item in resolved_items:
        if item.get("resolved") and item["resolved"] != item["chosen"]:
            key = (item["chapter"], item["paragraph"])
            per_para[key].append((item["chosen"], item["resolved"]))

    if not per_para:
        print("    No corrections to apply")
        return

    # Apply corrections to chapter text
    applied = 0
    for ch in chapters:
        ch_id = ch["id"]
        paras = ch["text"].split("\n\n")
        modified = False

        for para_idx, para in enumerate(paras):
            corrections = per_para.get((ch_id, para_idx))
            if not corrections:
                continue

            words = para.split()
            new_words = list(words)
            # Track which word positions have been corrected
            corrected_positions = set()

            for old_word, new_word in corrections:
                # Find the first uncorrected occurrence
                for i, w in enumerate(words):
                    if i not in corrected_positions and w == old_word:
                        new_words[i] = new_word
                        corrected_positions.add(i)
                        applied += 1
                        modified = True
                        break

            paras[para_idx] = " ".join(new_words)

        if modified:
            ch["text"] = "\n\n".join(paras)

    # Write updated chapters
    from utils import atomic_write_json

    atomic_write_json(chapters_path, chapters)
    print(f"    Applied {applied} corrections to reconciled_chapters.json")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", help="Anthropic API key")
    parser.add_argument("--batch-size", type=int, default=5)
    args = parser.parse_args()

    base = Path(__file__).parent
    triage_items(base / "data", api_key=args.api_key, batch_size=args.batch_size)
