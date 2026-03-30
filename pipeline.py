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
    "adjudicate", "validate", "translate", "typeset", "all",
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
        help="Run LLM cleanup on a single chapter only (e.g. p2_ch21)",
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
    args = parser.parse_args()

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

        reconcile(DATA_DIR)
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

        translate(OUTPUT_DIR, STATE_DIR, api_key=args.api_key)
        print()

    if args.step in ("typeset", "all"):
        print("Step 8: Typesetting bilingual edition...")
        from typeset import typeset

        typeset(OUTPUT_DIR)
        print()

    print("Done!")


if __name__ == "__main__":
    main()
