# book-engine

A book/language-agnostic OCR → reconcile → clean → translate → typeset framework,
**forked one-way** from the *Per la Libertà!* pipeline at the parent-repo root.

The parent pipeline is built for one book (1913 Italian); dozens of constants encode
facts about that single book/language/scan. This package lifts every such constant out
of the core into a **per-book manifest** + **shared profiles**, so the same machinery
can build future books in other languages without touching — or risking — the live
*Per la Libertà!* edition.

> **Status: scaffold (M0).** The package imports cleanly and ships a runnable (empty)
> test suite; the step modules are stubs that raise `NotImplementedError` until ported.
> See `../ENGINE_FRAMEWORK_PLAN.md` for the staged build (M0–M7) and the design rationale.

## Governance

This is a **deliberate forward fork, not a maintained mirror.** The live parent tree
remains the source of truth until *Per la Libertà!* is frozen. Fixes in the live tree
are **not** backported here unless they correct generic-engine behavior. There is no
bidirectional sync; the only sanctioned cross-flow is refreshing the frozen golden
fixtures under `books/per_la_liberta/inputs/` from live (read-only).

## Layout

```
src/engine/        importable package (true src layout) — names no book; reads cfg + LanguagePlugin
  cli.py           orchestrator (replaces pipeline.py)
  paths.py         BookWorkspace — all artifacts under books/<id>/work/ only
  config/          BookManifest / LanguageProfile / ScanProfile / TypefaceProfile + JSON-schema validation
  prompts/         Jinja2 StrictUndefined templating
  lang/            LanguagePlugin ABC + Italian impl (ordinals, headings, ChapterIdentity)
  steps/           the ported pipeline steps
  dictionaries/    chunked period-dict loader + >=2-of-N membership oracle (reusable)
  review/          native-resolution scan re-read layer (reusable review primitive)
  util/            generic helpers ported from utils.py, split by concern
  contracts/       versioned sidecar schemas + id/path-shape assertions
profiles/          SHARED reusable knowledge (languages / typefaces / prompt templates)
books/<id>/        per-book manifest + hand-curated sidecars + isolated work/{data,output,state}
assets/            dev-time symlinks to read-only heavy assets (real copies at extraction)
tests/{unit,golden,fixtures}
```

## Develop

```bash
cd engine
uv sync --extra it          # installs the engine + Italian spaCy model
uv run pytest tests/unit    # fast unit tests
uv run pytest tests/golden  # golden reproduction tests (slow; -m golden)
```

The framework **never writes outside `books/<id>/work/`**. `paths.BookWorkspace`
asserts workspace containment, and `tests/unit/test_isolation.py` hashes the protected
parent roots (`data/`, `output/`, `state/`, `docs/`, `static/`) before/after each step
and fails on any mutation. Read-only heavy assets are symlinked under `assets/` during
development; real copies land only at extraction (`git subtree split --prefix=engine`).
