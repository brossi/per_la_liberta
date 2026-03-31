"""Main orchestrator for the OCR reconciliation and translation pipeline."""

import argparse
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
STATE_DIR = BASE_DIR / "state"

STEPS = [
    "download", "ocr", "reconcile", "triage", "cleanup",
    "adjudicate", "validate", "translate", "refine", "typeset", "all",
]


def main():
    parser = argparse.ArgumentParser(
        description="Per la Libertà! — OCR reconciliation and translation pipeline"
    )
    parser.add_argument(
        "--step",
        choices=STEPS,
        default="all",
        help="Which pipeline step to run (default: all)",
    )
    parser.add_argument(
        "--api-key",
        help="Anthropic API key (or set ANTHROPIC_API_KEY env var)",
    )
    parser.add_argument(
        "--gemini-api-key",
        help="Gemini API key (or set GEMINI_API_KEY env var)",
    )
    parser.add_argument(
        "--llm-cleanup",
        action="store_true",
        help="Use LLM to correct Italian text during cleanup (requires API key)",
    )
    parser.add_argument(
        "--chapter",
        help="Run reconcile/cleanup on specific chapters, comma-separated (e.g. p1_ch01,p1_ch02)",
    )
    parser.add_argument(
        "--skip-ocr",
        action="store_true",
        help="Skip OCR step (use existing copy3_raw.txt or fall back to 2-way)",
    )
    parser.add_argument(
        "--no-triage",
        action="store_true",
        help="Skip LLM triage (majority vote only)",
    )
    parser.add_argument(
        "--workers", type=int, default=1,
        help="Concurrent translation workers (default: 1)",
    )
    parser.add_argument(
        "--thinking-budget", type=int, default=4096,
        help="Translation thinking budget in tokens (default: 4096)",
    )
    parser.add_argument(
        "--no-thinking", action="store_true",
        help="Disable extended thinking for translation",
    )
    parser.add_argument(
        "--with-edgren", action="store_true",
        help="Enrich translation prompts with Edgren 1901 dictionary context",
    )
    parser.add_argument(
        "--revert-to", type=int,
        help="Revert translations to a prior snapshot version (use with --step refine)",
    )
    parser.add_argument(
        "--local", action="store_true",
        help="Generate QR codes pointing to localhost:8000 instead of GitHub Pages",
    )
    parser.add_argument(
        "--site-base",
        help="Base URL for QR codes (default: GitHub Pages URL, or localhost:8000 with --local)",
    )
    args = parser.parse_args()

    # Resolve chapter IDs: accept either short (p1_ch01) or long (p1_capitolo_primo)
    if args.chapter:
        raw_ids = [c.strip() for c in args.chapter.split(",")]
        italian_md = OUTPUT_DIR / "italian_clean.md"
        if italian_md.exists():
            from utils import resolve_chapter_ids
            ch_list = resolve_chapter_ids(raw_ids, italian_md)
        else:
            ch_list = raw_ids  # fallback for early pipeline steps
    else:
        ch_list = None

    if args.step in ("download", "all"):
        print("Step 1: Downloading OCR texts...")
        from download import download_texts

        download_texts(DATA_DIR)
        print()

    if args.step in ("ocr", "all"):
        if args.skip_ocr:
            print("Step 2: OCR skipped (--skip-ocr)")
        else:
            from ocr import DEFAULT_PDF, ocr_pdf

            pdf_path = BASE_DIR / DEFAULT_PDF
            if not pdf_path.exists():
                print(f"Step 2: Warning: PDF not found at {pdf_path}, skipping OCR")
            else:
                # Flash pass: fast page mapping
                flash_path = DATA_DIR / "copy3_flash.txt"
                if flash_path.exists():
                    print(f"Step 2a: Flash OCR already complete ({flash_path.stat().st_size:,} bytes)")
                else:
                    print("Step 2a: Running Gemini Flash OCR (page mapping)...")
                    ocr_pdf(pdf_path, flash_path, api_key=args.gemini_api_key, model="flash")

                # Pro pass: quality third witness
                pro_path = DATA_DIR / "copy3_raw.txt"
                if pro_path.exists():
                    print(f"Step 2b: Pro OCR already complete ({pro_path.stat().st_size:,} bytes)")
                else:
                    print("Step 2b: Running Gemini Pro OCR (quality witness)...")
                    ocr_pdf(pdf_path, pro_path, api_key=args.gemini_api_key, model="pro")
        print()

    if args.step in ("reconcile", "all"):
        print("Step 3: Reconciling OCR copies...")
        from reconcile import reconcile

        ch_list = [c.strip() for c in args.chapter.split(",")] if args.chapter else None
        reconcile(DATA_DIR, chapters=ch_list)
        print()

    if args.step in ("triage", "all"):
        if args.no_triage:
            print("Step 4: Triage skipped (--no-triage)")
        else:
            print("Step 4: LLM triage of flagged disagreements...")
            from triage import triage_items

            triage_items(DATA_DIR, api_key=args.api_key)
        print()

    if args.step in ("cleanup", "all"):
        print("Step 5: Cleaning up OCR artifacts...")
        from cleanup import cleanup

        cleanup(DATA_DIR, OUTPUT_DIR, use_llm=args.llm_cleanup, api_key=args.api_key, chapter=args.chapter)
        if args.llm_cleanup:
            from cleanup import reconcile_flags

            reconcile_flags(DATA_DIR, OUTPUT_DIR)
        print()

    if args.step in ("adjudicate", "all"):
        print("Step 5b: Adjudicating unresolved hyphenated tokens...")
        from adjudicate import adjudicate

        results = adjudicate(DATA_DIR)
        if results:
            from utils import atomic_write_json

            atomic_write_json(DATA_DIR / "adjudication_results.json", results)
        print()

    if args.step in ("validate", "all"):
        print("Step 6: Validating cleaned text...")
        from validate import validate

        validate(OUTPUT_DIR, DATA_DIR)
        print()

    if args.step in ("translate", "all"):
        print("Step 7: Translating to English...")
        from translate import translate

        translate(
            OUTPUT_DIR, STATE_DIR, api_key=args.api_key,
            workers=args.workers, thinking_budget=args.thinking_budget,
            no_thinking=args.no_thinking,
            with_edgren=args.with_edgren,
        )
        print()

    # Refine is manual-only — never runs as part of "all"
    if args.step == "refine":
        if args.revert_to is not None:
            print(f"Step 7b: Reverting translations to version {args.revert_to}...")
            from refine import revert_to_version

            revert_to_version(args.revert_to, STATE_DIR, OUTPUT_DIR, chapters=ch_list)
        else:
            print("Step 7b: Refining translations with Edgren 1901...")
            from refine import refine

            refine(
                OUTPUT_DIR, STATE_DIR, chapters=ch_list,
                api_key=args.api_key, thinking_budget=args.thinking_budget,
            )
        print()

    if args.step in ("typeset", "all"):
        print("Step 8: Typesetting bilingual edition...")
        from typeset import typeset

        site_base = args.site_base or ("http://localhost:8000" if args.local else None)
        typeset(OUTPUT_DIR, STATE_DIR, site_base=site_base)
        print()

    print("Done!")


if __name__ == "__main__":
    main()
