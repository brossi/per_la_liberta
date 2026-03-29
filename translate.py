"""Step 4: Translate cleaned Italian text to English using Claude API."""

import json
import os
import re
import time
from pathlib import Path


def parse_italian_markdown(text: str) -> list[dict]:
    """Parse the Italian markdown into chapters for translation."""
    chapters = []
    current_chapter = None
    current_lines = []

    for line in text.split("\n"):
        # Detect chapter/section headers
        if line.startswith("## ") or line.startswith("### "):
            if current_chapter is not None:
                current_chapter["text"] = "\n".join(current_lines).strip()
                if current_chapter["text"]:
                    chapters.append(current_chapter)

            header_level = 2 if line.startswith("## ") else 3
            title = line.lstrip("#").strip()

            # Skip the book title and metadata
            if title in ("Per la Libertà!", "Parte Prima", "Parte Seconda"):
                current_chapter = {"id": title.lower().replace(" ", "_"), "title": title, "level": header_level, "is_structural": True}
                current_lines = []
                continue

            current_chapter = {
                "id": re.sub(r"[^a-z0-9]", "_", title.lower()).strip("_"),
                "title": title,
                "level": header_level,
                "is_structural": False,
            }
            current_lines = []
        elif current_chapter is not None:
            current_lines.append(line)

    if current_chapter is not None:
        current_chapter["text"] = "\n".join(current_lines).strip()
        if current_chapter["text"]:
            chapters.append(current_chapter)

    return [ch for ch in chapters if not ch.get("is_structural") or ch.get("text")]


def translate_chapter(text: str, title: str, api_key: str) -> tuple[str, str]:
    """Translate a single chapter from Italian to English.

    Returns (translated_text, stop_reason).
    """
    import anthropic

    from utils import retry_api_call

    client = anthropic.Anthropic(api_key=api_key, timeout=300.0)

    max_tokens = 128000
    thinking_budget = 32000

    def _call():
        return client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=max_tokens,
            thinking={
                "type": "enabled",
                "budget_tokens": thinking_budget,
            },
            system=(
                "You are translating a 1913 Italian book titled 'Per la Libertà!' (For Freedom!) "
                "by Cesare Crespi. It documents conversations with Count Carlo di Rudio about "
                "Italian unification, the Risorgimento, and the Orsini conspiracy against Napoleon III.\n\n"
                "Translation guidelines:\n"
                "- Produce a faithful, literary English translation\n"
                "- Maintain the early 20th century literary style and tone\n"
                "- Preserve all proper nouns, place names, and historical references in their original form "
                "(e.g., keep 'Felice Orsini', 'Mazzini', 'Radetzky', Italian place names)\n"
                "- Preserve paragraph structure\n"
                "- Translate footnotes in place\n"
                "- Do not add commentary or notes — output only the English translation\n"
                "- For Italian expressions that have no good English equivalent, keep the Italian "
                "in italics (using *asterisks*) with a brief inline gloss if needed"
            ),
            messages=[
                {
                    "role": "user",
                    "content": f"Translate the following chapter ({title}):\n\n{text}",
                }
            ],
        )

    response = retry_api_call(_call)

    translated = next(b.text for b in response.content if b.type == "text")
    return translated, response.stop_reason


def translate(output_dir: Path, state_dir: Path, api_key: str | None = None) -> None:
    """Translate Italian markdown to English, chapter by chapter."""
    from utils import atomic_write_json

    if not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("No API key. Set ANTHROPIC_API_KEY or pass --api-key.")

    italian_path = output_dir / "italian_clean.md"
    italian_text = italian_path.read_text(encoding="utf-8")

    chapters = parse_italian_markdown(italian_text)
    print(f"  Found {len(chapters)} translatable chapters")

    # Load or create progress file
    translations_dir = state_dir / "translations"
    translations_dir.mkdir(parents=True, exist_ok=True)
    progress_path = state_dir / "translation_progress.json"

    if progress_path.exists():
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
    else:
        progress = {}

    # Prune stale progress entries for chapters that no longer exist
    current_ids = {ch["id"] for ch in chapters}
    stale = [k for k in progress if k not in current_ids]
    if stale:
        for k in stale:
            del progress[k]
        atomic_write_json(progress_path, progress)
        print(f"  Pruned {len(stale)} stale progress entries")

    # Translate each chapter
    for i, ch in enumerate(chapters):
        ch_id = ch["id"]

        if progress.get(ch_id, {}).get("status") == "done":
            print(f"  [{i+1}/{len(chapters)}] {ch['title']}: already translated")
            continue

        print(f"  [{i+1}/{len(chapters)}] Translating: {ch['title']}...")

        progress[ch_id] = {"status": "in_progress"}
        atomic_write_json(progress_path, progress)

        try:
            # Extract page markers before translation, reinsert after.
            # Don't rely on the LLM to preserve HTML comments.
            page_marker = ""
            page_match = re.search(r"<!-- pages:\d+-\d+ -->", ch["text"])
            if page_match:
                page_marker = page_match.group(0)
            text_for_translation = re.sub(r"<!-- pages:\d+-\d+ -->\n?", "", ch["text"])

            translated, stop_reason = translate_chapter(text_for_translation, ch["title"], api_key)

            # Reinsert page marker at the top of the translated text
            if page_marker:
                translated = page_marker + "\n\n" + translated

            # Save individual chapter translation
            ch_path = translations_dir / f"{ch_id}.md"
            ch_path.write_text(translated, encoding="utf-8")

            # Detect truncation
            if stop_reason == "max_tokens":
                print(f"    WARNING: Translation truncated (hit max_tokens)")
                progress[ch_id] = {"status": "truncated", "file": str(ch_path.name)}
            elif len(translated) / max(len(ch["text"]), 1) < 0.3:
                print(f"    WARNING: Translation suspiciously short ({len(translated):,} vs {len(ch['text']):,} input chars)")
                progress[ch_id] = {"status": "truncated", "file": str(ch_path.name)}
            else:
                progress[ch_id] = {"status": "done", "file": str(ch_path.name)}

            atomic_write_json(progress_path, progress)

            print(f"    Done ({len(translated):,} chars)")
            time.sleep(1)  # Rate limiting

        except Exception as e:
            print(f"    Error: {e}")
            progress[ch_id] = {"status": "error", "error": str(e)}
            atomic_write_json(progress_path, progress)

    # Assemble final English markdown
    assemble_translation(output_dir, state_dir, chapters)


def assemble_translation(
    output_dir: Path, state_dir: Path, chapters: list[dict]
) -> None:
    """Assemble individual chapter translations into final English markdown."""
    translations_dir = state_dir / "translations"

    md_lines = [
        "# For Freedom!",
        "",
        "*From my conversations with Count Carlo di Rudio, accomplice of Felice Orsini*",
        "",
        "**Cesare Crespi** (1913)",
        "",
        "*Translated from the Italian*",
        "",
        "---",
        "",
    ]

    for ch in chapters:
        ch_path = translations_dir / f"{ch['id']}.md"
        if not ch_path.exists():
            print(f"  Warning: Missing translation for {ch['id']}")
            continue

        translated = ch_path.read_text(encoding="utf-8")

        # Add header
        level = "#" * ch["level"]
        # Translate structural titles
        title = ch["title"]
        title_map = {
            "Prefazione": "Preface",
            "Parte Prima": "Part One",
            "Parte Seconda": "Part Two",
        }
        display_title = title_map.get(title, title)

        md_lines.extend([f"{level} {display_title}", ""])
        md_lines.append(translated)
        md_lines.extend(["", ""])

    output_path = output_dir / "english_translation.md"
    output_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"\n  English translation: {output_path}")

    # Generate source_pages.json sidecar with IA links
    _generate_source_pages(output_dir, "\n".join(md_lines))


IA_ITEM_ID = "perlalibertdal00cres"


def _generate_source_pages(output_dir: Path, markdown_text: str) -> None:
    """Extract page references from markdown and generate source_pages.json."""
    import re

    page_refs = re.findall(
        r"^(#{2,3}\s.+)\n[\s\S]*?<!-- pages:(\d+)-(\d+) -->",
        markdown_text,
        re.MULTILINE,
    )

    if not page_refs:
        return

    source_pages = {}
    for header, start_page, end_page in page_refs:
        title = header.lstrip("#").strip()
        ch_id = re.sub(r"[^a-z0-9]", "_", title.lower()).strip("_")
        start = int(start_page)
        end = int(end_page)
        # IA uses 0-indexed page numbers in URLs
        source_pages[ch_id] = {
            "title": title,
            "pages": list(range(start, end + 1)),
            "ia_url": f"https://archive.org/details/{IA_ITEM_ID}/page/n{start - 1}/mode/1up",
        }

    sidecar_path = output_dir / "source_pages.json"
    sidecar_path.write_text(
        json.dumps(source_pages, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  Source pages sidecar: {sidecar_path} ({len(source_pages)} chapters)")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", help="Anthropic API key")
    args = parser.parse_args()

    base = Path(__file__).parent
    translate(base / "output", base / "state", api_key=args.api_key)
