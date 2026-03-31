"""Post-hoc translation refinement with Edgren 1901 dictionary context.

Reviews existing English translations against period-appropriate Italian-English
definitions, producing targeted revisions with full version tracking.

Usage:
    python pipeline.py --step refine --chapter p1_capitolo_primo
    python pipeline.py --step refine                     # all chapters
    python pipeline.py --step refine --revert-to 1       # revert to version 1
"""

import json
import os
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from edgren import (
    chunk_edgren,
    edgren_entries_for_words,
    extract_content_words,
    format_edgren_context,
)
from translate import assemble_translation, parse_italian_markdown


# ── Prompts ───────────────────────────────────────────────────────────

REFINE_SYSTEM_PROMPT = (
    "You are reviewing an English translation of a 1913 Italian book titled "
    "'Per la Libertà!' by Cesare Crespi. The book documents conversations with "
    "Count Carlo di Rudio about Italian unification and the Orsini conspiracy.\n\n"
    "You have been given:\n"
    "1. The original Italian text\n"
    "2. The current English translation\n"
    "3. Period-appropriate definitions from the Edgren Italian-English Dictionary (1901)\n\n"
    "Your task is to review the translation and make MINIMAL, TARGETED revisions "
    "where the Edgren dictionary evidence suggests a more period-appropriate or "
    "accurate English rendering.\n\n"
    "Guidelines:\n"
    "- PRESERVE the existing translation wherever it is acceptable. Most of it will be fine.\n"
    "- Only change words or phrases where the 1901 dictionary clearly suggests a "
    "better period-appropriate English equivalent.\n"
    "- Do NOT rewrite sentences for style. Do NOT modernize. Do NOT add commentary.\n"
    "- Maintain paragraph structure exactly.\n"
    "- For each change, wrap the NEW text in a <change> tag with the old text and reason:\n"
    '  <change old="previous text" reason="Edgren: word = definition">new text</change>\n'
    "- If no changes are warranted for a paragraph, reproduce it exactly as-is.\n"
    "- Output the complete revised translation with <change> tags inline."
)


# ── Revision tracking ─────────────────────────────────────────────────

REVISIONS_DIR_NAME = "translation_revisions"


def _revisions_dir(state_dir: Path) -> Path:
    return state_dir / REVISIONS_DIR_NAME


def _load_revision_log(state_dir: Path) -> dict:
    log_path = _revisions_dir(state_dir) / "revision_log.json"
    if log_path.exists():
        return json.loads(log_path.read_text(encoding="utf-8"))
    return {"current_version": 1, "revisions": []}


def _save_revision_log(state_dir: Path, log: dict) -> None:
    from utils import atomic_write_json
    log_path = _revisions_dir(state_dir) / "revision_log.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(log_path, log)


def _create_snapshot(state_dir: Path, log: dict, source: str, scope: list[str]) -> int:
    """Snapshot current translations and record in revision log.

    Returns the new version number.
    """
    translations_dir = state_dir / "translations"
    if not translations_dir.exists():
        raise FileNotFoundError(f"No translations directory at {translations_dir}")

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    snapshot_dir = _revisions_dir(state_dir) / "snapshots" / timestamp
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    # Copy all .md files
    count = 0
    for md_file in translations_dir.glob("*.md"):
        shutil.copy2(md_file, snapshot_dir / md_file.name)
        count += 1

    version = log["current_version"]
    log["revisions"].append({
        "version": version,
        "timestamp": timestamp,
        "source": source,
        "scope": scope,
        "snapshot_dir": timestamp,
    })
    log["current_version"] = version + 1
    _save_revision_log(state_dir, log)

    print(f"  Snapshot v{version}: {count} files → {snapshot_dir.name}")
    return version


def _save_changes(state_dir: Path, version: int, chapter_id: str,
                  changes: list[dict], model: str) -> None:
    """Save change metadata for a chapter revision."""
    from utils import atomic_write_json

    changes_dir = _revisions_dir(state_dir) / "changes"
    changes_dir.mkdir(parents=True, exist_ok=True)

    data = {
        "version": version + 1,  # changes produce the NEXT version
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "chapter_id": chapter_id,
        "source": "edgren_refinement",
        "model": model,
        "changes": changes,
    }
    path = changes_dir / f"v{version + 1}_{chapter_id}.json"
    atomic_write_json(path, data)


# ── Change parsing ────────────────────────────────────────────────────

_CHANGE_RE = re.compile(
    r'<change\s+old="([^"]*?)"\s+reason="([^"]*?)">(.*?)</change>',
    re.DOTALL,
)


def _parse_changes(revised_text: str, original_text: str) -> tuple[str, list[dict]]:
    """Extract <change> tags from revised text.

    Returns (clean_text, changes_list) where clean_text has tags stripped
    and changes_list contains {old, new, reason, context_sentence} dicts.
    """
    changes = []
    clean = revised_text

    for match in _CHANGE_RE.finditer(revised_text):
        old_text = match.group(1)
        reason = match.group(2)
        new_text = match.group(3)

        # Extract a context sentence (the surrounding ~100 chars)
        start = max(0, match.start() - 50)
        end = min(len(revised_text), match.end() + 50)
        context = revised_text[start:end]
        # Clean tags from context
        context = _CHANGE_RE.sub(r"\3", context).strip()

        changes.append({
            "old": old_text,
            "new": new_text,
            "reason": reason,
            "context_sentence": context,
        })

    # Strip all <change> tags, keeping the new text
    clean = _CHANGE_RE.sub(r"\3", clean)

    # Fallback: if no tags found but text differs, use difflib
    if not changes and clean.strip() != original_text.strip():
        changes = _diff_fallback(original_text, clean)

    return clean, changes


def _diff_fallback(original: str, revised: str) -> list[dict]:
    """Sentence-level diff when Claude doesn't use <change> tags."""
    import difflib

    orig_sentences = re.split(r"(?<=[.!?])\s+", original)
    rev_sentences = re.split(r"(?<=[.!?])\s+", revised)

    changes = []
    matcher = difflib.SequenceMatcher(None, orig_sentences, rev_sentences)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "replace":
            old = " ".join(orig_sentences[i1:i2])
            new = " ".join(rev_sentences[j1:j2])
            changes.append({
                "old": old,
                "new": new,
                "reason": "Changed (no dictionary annotation provided)",
                "context_sentence": new[:100],
            })
    return changes


# ── Refinement pipeline ──────────────────────────────────────────────

def _refine_chapter(
    italian_text: str, english_text: str, edgren_ctx: str,
    title: str, api_key: str, thinking_budget: int = 4096,
) -> tuple[str, str]:
    """Send a chapter for refinement via Claude.

    Returns (revised_text_with_tags, stop_reason).
    """
    import anthropic

    from utils import retry_api_call

    client = anthropic.Anthropic(api_key=api_key, timeout=600.0)

    user_content = (
        f"## Italian Source ({title})\n\n{italian_text}\n\n"
        f"## Current English Translation\n\n{english_text}\n\n"
        f"## Edgren 1901 Dictionary Reference\n\n{edgren_ctx}"
    )

    kwargs = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 128000,
        "system": REFINE_SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_content}],
        "thinking": {"type": "enabled", "budget_tokens": thinking_budget},
    }

    def _call():
        return client.messages.create(**kwargs)

    response = retry_api_call(_call)
    text = next(b.text for b in response.content if b.type == "text")
    return text, response.stop_reason


def refine(
    output_dir: Path, state_dir: Path,
    chapters: list[str] | None = None,
    api_key: str | None = None,
    thinking_budget: int = 4096,
) -> None:
    """Refine translations using Edgren 1901 dictionary context.

    Args:
        output_dir: Directory containing italian_clean.md
        state_dir: Directory containing translations/ and revision tracking
        chapters: List of chapter IDs to refine (None = all)
        api_key: Anthropic API key
        thinking_budget: Thinking tokens for Claude
    """
    from utils import atomic_write_json

    if not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("No API key. Set ANTHROPIC_API_KEY or pass --api-key.")

    # Ensure Edgren dictionary is ready
    chunk_edgren()

    # Parse Italian source
    italian_path = output_dir / "italian_clean.md"
    italian_text = italian_path.read_text(encoding="utf-8")
    italian_chapters = parse_italian_markdown(italian_text)
    italian_by_id = {ch["id"]: ch for ch in italian_chapters}

    # Load existing translations
    translations_dir = state_dir / "translations"
    if not translations_dir.exists():
        raise FileNotFoundError("No translations found. Run --step translate first.")

    # Determine scope
    if chapters:
        scope = chapters
    else:
        scope = [ch["id"] for ch in italian_chapters if not ch.get("is_structural")]
    print(f"  Refining {len(scope)} chapters with Edgren 1901 context")

    # Snapshot before changes
    log = _load_revision_log(state_dir)
    snapshot_version = _create_snapshot(state_dir, log, "pre_refinement", scope)

    total_changes = 0
    for idx, ch_id in enumerate(scope):
        # Load Italian source
        it_ch = italian_by_id.get(ch_id)
        if not it_ch:
            print(f"  [{idx+1}/{len(scope)}] {ch_id}: Italian source not found, skipping")
            continue

        it_text = re.sub(r"<!-- pages:\d+-\d+ -->\n?", "", it_ch["text"])

        # Load English translation
        en_path = translations_dir / f"{ch_id}.md"
        if not en_path.exists():
            print(f"  [{idx+1}/{len(scope)}] {ch_id}: Translation not found, skipping")
            continue
        en_text = en_path.read_text(encoding="utf-8")
        # Strip page marker for comparison
        en_text_clean = re.sub(r"<!-- pages:\d+-\d+ -->\n*", "", en_text)

        # Build Edgren context
        words = extract_content_words(it_text)
        entries = edgren_entries_for_words(words)
        if not entries:
            print(f"  [{idx+1}/{len(scope)}] {ch_id}: No Edgren entries found, skipping")
            continue

        edgren_ctx = format_edgren_context(entries)
        print(f"  [{idx+1}/{len(scope)}] {ch_id}: {len(entries)} Edgren entries, sending to Claude...")

        t0 = time.monotonic()
        revised_with_tags, stop_reason = _refine_chapter(
            it_text, en_text_clean, edgren_ctx,
            it_ch["title"], api_key, thinking_budget,
        )
        elapsed = time.monotonic() - t0

        # Parse changes
        clean_text, changes = _parse_changes(revised_with_tags, en_text_clean)

        # Reinsert page marker
        page_match = re.search(r"<!-- pages:\d+-\d+ -->", en_text)
        if page_match:
            clean_text = page_match.group(0) + "\n\n" + clean_text

        # Save revised translation
        en_path.write_text(clean_text, encoding="utf-8")

        # Save change metadata
        if changes:
            _save_changes(state_dir, snapshot_version, ch_id, changes, "claude-sonnet-4-6")

        total_changes += len(changes)
        print(f"  [{idx+1}/{len(scope)}] {ch_id}: {len(changes)} changes [{elapsed:.1f}s]")

    print(f"\n  Refinement complete: {total_changes} total changes across {len(scope)} chapters")

    # Reassemble english_translation.md
    print("  Reassembling english_translation.md...")
    assemble_translation(output_dir, state_dir, italian_chapters)


# ── Revert ────────────────────────────────────────────────────────────

def revert_to_version(version: int, state_dir: Path, output_dir: Path,
                      chapters: list[str] | None = None) -> None:
    """Revert translations to a prior snapshot version.

    Args:
        version: Snapshot version number to revert to.
        state_dir: Directory containing translations/ and revision tracking.
        output_dir: Directory containing italian_clean.md for reassembly.
        chapters: Optional list of chapter IDs to revert. If None, reverts all.
    """
    log = _load_revision_log(state_dir)

    # Find the snapshot for the requested version
    target = None
    for rev in log["revisions"]:
        if rev["version"] == version:
            target = rev
            break

    if not target:
        available = [r["version"] for r in log["revisions"]]
        raise ValueError(f"Version {version} not found. Available: {available}")

    snapshot_dir = _revisions_dir(state_dir) / "snapshots" / target["snapshot_dir"]
    if not snapshot_dir.exists():
        raise FileNotFoundError(f"Snapshot directory missing: {snapshot_dir}")

    translations_dir = state_dir / "translations"
    count = 0
    if chapters:
        # Selective revert: only restore specified chapters
        for ch_id in chapters:
            src = snapshot_dir / f"{ch_id}.md"
            if src.exists():
                shutil.copy2(src, translations_dir / src.name)
                count += 1
            else:
                print(f"  Warning: {ch_id}.md not found in snapshot v{version}")
        scope = chapters
    else:
        for md_file in snapshot_dir.glob("*.md"):
            shutil.copy2(md_file, translations_dir / md_file.name)
            count += 1
        scope = ["all"]

    # Log the revert as a new revision
    log["revisions"].append({
        "version": log["current_version"],
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S"),
        "source": f"revert_to_v{version}",
        "scope": scope,
        "snapshot_dir": target["snapshot_dir"],
    })
    log["current_version"] += 1
    _save_revision_log(state_dir, log)

    print(f"  Reverted {count} files to version {version}")

    # Reassemble
    italian_path = output_dir / "italian_clean.md"
    italian_text = italian_path.read_text(encoding="utf-8")
    italian_chapters = parse_italian_markdown(italian_text)
    assemble_translation(output_dir, state_dir, italian_chapters)
    print("  Reassembled english_translation.md")


# ── CLI ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Refine translations with Edgren 1901")
    parser.add_argument("--chapter", help="Comma-separated chapter IDs")
    parser.add_argument("--api-key", help="Anthropic API key")
    parser.add_argument("--thinking-budget", type=int, default=4096)
    parser.add_argument("--revert-to", type=int, help="Revert to version N")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv()

    base = Path(__file__).parent
    output_dir = base / "output"
    state_dir = base / "state"

    if args.revert_to is not None:
        ch_list = [c.strip() for c in args.chapter.split(",")] if args.chapter else None
        revert_to_version(args.revert_to, state_dir, output_dir, chapters=ch_list)
    else:
        ch_list = [c.strip() for c in args.chapter.split(",")] if args.chapter else None
        refine(output_dir, state_dir, chapters=ch_list,
               api_key=args.api_key, thinking_budget=args.thinking_budget)
