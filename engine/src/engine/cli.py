"""Orchestrator CLI — the engine's replacement for the top-level ``pipeline.py``.

Responsibilities (built out across milestones):
  1. parse args (``--book``, ``--step``, step options);
  2. resolve the book → ``ResolvedConfig`` + ``LanguagePlugin`` (M1);
  3. derive an isolated ``BookWorkspace`` under ``books/<id>/work/`` (M1);
  4. dispatch to ``engine.steps.<step>.run(ws, cfg, lang, **opts)``.

M0 scaffold: this provides the real argparse shape and step dispatch, but the
steps themselves are stubs (each ``run`` raises NotImplementedError until ported),
and book resolution / workspace derivation arrive in M1.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

from engine import STEPS
from engine.config.loader import ConfigError, load_book
from engine.lang.registry import get_language_plugin
from engine.paths import BookWorkspace

PACKAGE_ROOT = Path(__file__).resolve().parent
ENGINE_ROOT = PACKAGE_ROOT.parents[1]  # engine/ (src/engine/cli.py -> engine/)
BOOKS_DIR = ENGINE_ROOT / "books"


def _available_books() -> list[str]:
    """Book ids are the directory names under engine/books/ holding a manifest."""
    if not BOOKS_DIR.is_dir():
        return []
    return sorted(
        p.name for p in BOOKS_DIR.iterdir() if (p / "manifest.json").is_file()
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="engine",
        description="Book/language-agnostic OCR → translate → typeset framework.",
    )
    parser.add_argument(
        "--book",
        default="per_la_liberta",
        help="Book id under engine/books/ (default: per_la_liberta).",
    )
    parser.add_argument(
        "--step",
        choices=(*STEPS, "all"),
        help="Pipeline step to run (or 'all' for the full build subset).",
    )
    parser.add_argument(
        "--list-books",
        action="store_true",
        help="List the configured books and exit.",
    )
    return parser


def _run_step(step: str, book: str) -> int:
    """Resolve the book, then dispatch to the named step module.

    M1 wires real resolution: the book's manifest + profiles become a ``ResolvedConfig``,
    its language id selects the ``LanguagePlugin``, and an isolated ``BookWorkspace`` is
    derived. Steps are ported milestone by milestone; until then their stubs raise
    ``NotImplementedError`` (surfaced as exit 2) even though resolution now succeeds.
    """
    try:
        cfg = load_book(book, books_dir=BOOKS_DIR)
    except ConfigError as exc:
        print(f"engine: {exc}", file=sys.stderr)
        return 1

    lang = get_language_plugin(cfg.language_id)
    workspace = BookWorkspace.for_book(book, BOOKS_DIR)

    module = importlib.import_module(f"engine.steps.{step}")
    try:
        module.run(workspace=workspace, cfg=cfg, lang=lang)
    except NotImplementedError as exc:
        print(f"engine: {exc}", file=sys.stderr)
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.list_books:
        for book in _available_books():
            print(book)
        return 0

    if not args.step:
        print("engine: nothing to do (pass --step or --list-books).", file=sys.stderr)
        return 1

    steps = list(STEPS) if args.step == "all" else [args.step]
    rc = 0
    for step in steps:
        rc = _run_step(step, args.book) or rc
    return rc


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
