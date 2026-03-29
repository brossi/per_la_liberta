"""Main orchestrator for the OCR reconciliation and translation pipeline."""

import argparse
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
STATE_DIR = BASE_DIR / "state"


def main():
    parser = argparse.ArgumentParser(
        description="Per la Libertà! — OCR reconciliation and translation pipeline"
    )
    parser.add_argument(
        "--step",
        choices=["download", "reconcile", "cleanup", "translate", "all"],
        default="all",
        help="Which pipeline step to run (default: all)",
    )
    parser.add_argument(
        "--api-key",
        help="Anthropic API key (or set ANTHROPIC_API_KEY env var)",
    )
    parser.add_argument(
        "--llm-cleanup",
        action="store_true",
        help="Use LLM to correct Italian text during cleanup (requires API key)",
    )
    args = parser.parse_args()

    if args.step in ("download", "all"):
        print("Step 1: Downloading OCR texts...")
        from download import download_texts

        download_texts(DATA_DIR)
        print()

    if args.step in ("reconcile", "all"):
        print("Step 2: Reconciling two OCR copies...")
        from reconcile import reconcile

        reconcile(DATA_DIR)
        print()

    if args.step in ("cleanup", "all"):
        print("Step 3: Cleaning up OCR artifacts...")
        from cleanup import cleanup

        cleanup(DATA_DIR, OUTPUT_DIR, use_llm=args.llm_cleanup, api_key=args.api_key)
        print()

    if args.step in ("translate", "all"):
        print("Step 4: Translating to English...")
        from translate import translate

        translate(OUTPUT_DIR, STATE_DIR, api_key=args.api_key)
        print()

    print("Done!")


if __name__ == "__main__":
    main()
