"""One-time extraction of narrative context from the Italian source text.

Runs per-chapter, asking Gemini Pro to extract characters, events, locations,
and relationships with mandatory Italian-language citations from the source.

Usage:
    uv run python extract_context.py
    uv run python extract_context.py --chapter p1_ch01,p1_ch02
"""

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from translate import parse_italian_markdown

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
STATE_DIR = BASE_DIR / "state"

EXTRACTION_PROMPT = """\
You are extracting narrative context from a chapter of a 1913 Italian book \
titled 'Per la Libertà!' by Cesare Crespi. The book records conversations \
with Count Carlo di Rudio about the Risorgimento and the Orsini conspiracy.

## Italian Source Text (Chapter: {title})
{italian_text}

## Task

Extract ALL of the following from this chapter. For every claim, you MUST \
provide an exact Italian quote from the source text above as citation evidence. \
The quote must be long enough to locate via text search (minimum 8 words).

Respond with valid JSON in this exact structure:
{{
  "chapter": "{chapter_id}",
  "characters": [
    {{
      "name": "<full name as given in text>",
      "aliases": ["<other names/titles used in this chapter>"],
      "role": "<role or description, based only on what this chapter says>",
      "citation": "<exact Italian quote from the text that introduces or describes this character>"
    }}
  ],
  "events": [
    {{
      "name": "<event name>",
      "date": "<date if mentioned, else null>",
      "description": "<what happened, based only on what this chapter says>",
      "citation": "<exact Italian quote referencing this event>"
    }}
  ],
  "locations": [
    {{
      "name": "<place name as it appears in Italian>",
      "english": "<English equivalent if obvious, else null>",
      "context": "<how this location relates to the narrative>",
      "citation": "<exact Italian quote mentioning this location>"
    }}
  ],
  "relationships": [
    {{
      "person_a": "<name>",
      "person_b": "<name>",
      "relationship": "<description: spouse, parent, co-conspirator, etc.>",
      "citation": "<exact Italian quote establishing this relationship>"
    }}
  ],
  "terminology": [
    {{
      "italian_term": "<the term as used in the text>",
      "meaning": "<what it means in context>",
      "citation": "<exact Italian quote using this term>"
    }}
  ]
}}

Rules:
- Extract ONLY what is explicitly stated in this chapter. Do not infer or add \
background knowledge.
- Every citation must be a verbatim substring of the source text above.
- If a character appears but nothing is said about them beyond their name, still \
include them with a minimal citation showing where the name appears.
- Include historical figures mentioned in passing (Mazzini, Garibaldi, etc.) \
with their citation.
- For terminology, focus on Italian political, military, legal, or cultural \
terms that a translator would need to handle consistently.
"""


def extract_chapter(
    chapter_id: str,
    title: str,
    italian_text: str,
    api_key: str | None = None,
) -> dict:
    """Extract narrative context from a single chapter via Gemini Pro."""
    from google import genai
    from google.genai import types
    from utils import retry_api_call

    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise ValueError("No Gemini API key. Set GEMINI_API_KEY.")
    client = genai.Client(api_key=key)

    prompt = EXTRACTION_PROMPT.format(
        title=title,
        chapter_id=chapter_id,
        italian_text=italian_text,
    )

    config = types.GenerateContentConfig(
        system_instruction="You are a meticulous literary analyst. Respond only with valid JSON. Every claim must include a verbatim Italian citation.",
        max_output_tokens=16_384,
        response_mime_type="application/json",
    )

    try:
        from google.api_core.exceptions import (
            InternalServerError,
            ResourceExhausted,
            ServiceUnavailable,
            TooManyRequests,
        )
        retryable = (ResourceExhausted, ServiceUnavailable,
                     InternalServerError, TooManyRequests)
    except ImportError:
        retryable = (RuntimeError,)

    # Retry on JSON parse errors (up to 3 attempts)
    last_error = None
    for attempt in range(3):
        def _call():
            return client.models.generate_content(
                model="gemini-2.5-flash",
                contents=types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=prompt)],
                ),
                config=config,
            )

        response = retry_api_call(_call, retryable_exceptions=retryable)
        text = response.text.strip()

        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            last_error = e
            print(f"    JSON parse error attempt {attempt + 1}: {e}")
            if attempt < 2:
                time.sleep(2)

    raise RuntimeError(f"Extraction failed for {chapter_id} after 3 attempts: {last_error}")


def validate_citations(extraction: dict, italian_text: str) -> dict:
    """Check each citation against the source text, flagging mismatches."""
    stats = {"total": 0, "verified": 0, "failed": []}

    for section in ["characters", "events", "locations", "relationships", "terminology"]:
        for item in extraction.get(section, []):
            citation = item.get("citation", "")
            if not citation:
                continue
            stats["total"] += 1

            # Normalise whitespace for matching
            norm_citation = " ".join(citation.split())
            norm_source = " ".join(italian_text.split())

            if norm_citation in norm_source:
                stats["verified"] += 1
                item["_verified"] = True
            else:
                # Try a fuzzy substring (first 40 chars) in case of minor OCR differences
                prefix = norm_citation[:40]
                if prefix in norm_source:
                    stats["verified"] += 1
                    item["_verified"] = "partial"
                else:
                    item["_verified"] = False
                    stats["failed"].append({
                        "section": section,
                        "name": item.get("name") or item.get("italian_term") or item.get("person_a", ""),
                        "citation_preview": citation[:80],
                    })

    extraction["_citation_stats"] = stats
    return extraction


def main():
    import argparse
    from dotenv import load_dotenv

    load_dotenv()

    parser = argparse.ArgumentParser(description="Extract narrative context from Italian source")
    parser.add_argument("--chapter", help="Comma-separated chapter IDs (default: all)")
    parser.add_argument("--workers", type=int, default=4, help="Concurrent workers (default: 4)")
    parser.add_argument("--gemini-api-key", help="Gemini API key")
    args = parser.parse_args()

    italian_text = (OUTPUT_DIR / "italian_clean.md").read_text(encoding="utf-8")
    chapters = parse_italian_markdown(italian_text)

    if args.chapter:
        from utils import resolve_chapter_ids
        filter_ids = set(resolve_chapter_ids(
            [c.strip() for c in args.chapter.split(",")],
            OUTPUT_DIR / "italian_clean.md",
        ))
        chapters = [ch for ch in chapters if ch["id"] in filter_ids]

    print(f"Extracting narrative context from {len(chapters)} chapters...")

    output_dir = STATE_DIR / "context_extractions"
    output_dir.mkdir(parents=True, exist_ok=True)

    api_key = args.gemini_api_key

    def _process(ch):
        ch_id = ch["id"]
        out_path = output_dir / f"{ch_id}.json"
        if out_path.exists():
            print(f"  [{ch_id}] Already extracted, skipping")
            return ch_id, json.loads(out_path.read_text(encoding="utf-8"))

        # Strip page markers
        text = re.sub(r"<!-- pages:\d+-\d+ -->\n?", "", ch["text"])

        print(f"  [{ch_id}] Extracting...")
        t0 = time.monotonic()
        result = extract_chapter(ch_id, ch["title"], text, api_key)
        result = validate_citations(result, text)
        elapsed = time.monotonic() - t0

        stats = result.get("_citation_stats", {})
        print(f"  [{ch_id}] Done ({elapsed:.0f}s) — "
              f"{stats.get('verified', 0)}/{stats.get('total', 0)} citations verified")
        if stats.get("failed"):
            for f in stats["failed"]:
                print(f"    UNVERIFIED: {f['section']}/{f['name']}: {f['citation_preview']}")

        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        return ch_id, result

    results = {}
    if args.workers <= 1 or len(chapters) == 1:
        for ch in chapters:
            ch_id, result = _process(ch)
            results[ch_id] = result
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(_process, ch): ch for ch in chapters}
            for future in as_completed(futures):
                ch_id, result = future.result()
                results[ch_id] = result

    # Summary
    total_chars = sum(len(r.get("characters", [])) for r in results.values())
    total_events = sum(len(r.get("events", [])) for r in results.values())
    total_locs = sum(len(r.get("locations", [])) for r in results.values())
    total_rels = sum(len(r.get("relationships", [])) for r in results.values())
    total_terms = sum(len(r.get("terminology", [])) for r in results.values())
    total_citations = sum(r.get("_citation_stats", {}).get("total", 0) for r in results.values())
    verified = sum(r.get("_citation_stats", {}).get("verified", 0) for r in results.values())

    print(f"\nExtraction complete:")
    print(f"  {total_chars} characters, {total_events} events, {total_locs} locations, "
          f"{total_rels} relationships, {total_terms} terms")
    print(f"  Citations: {verified}/{total_citations} verified against source text")
    print(f"  Per-chapter JSONs saved to: {output_dir}/")


if __name__ == "__main__":
    main()
