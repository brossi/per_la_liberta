"""book-engine — a book/language-agnostic OCR → reconcile → clean → translate →
typeset framework.

Forked (deliberately, one-way) from the *Per la Libertà!* pipeline at the parent
repo root. Every book/language/scan-specific constant leaves the core and lives in
a per-book manifest + shared profiles; the core reads ``cfg`` (ResolvedConfig) and
the active ``LanguagePlugin`` only. See ENGINE_FRAMEWORK_PLAN.md for the staged
build (M0–M7). M0 is scaffold: the package imports cleanly and the step modules are
stubs that raise NotImplementedError until ported.
"""

from __future__ import annotations

__version__ = "0.0.1"

# The ordered build subset the framework reproduces (through typeset). `refine` is
# manual-only and never part of `--step all`; `companion` is intentionally excluded
# as situational hand-authored content (see plan "Decisions").
STEPS = (
    "download",
    "ocr",
    "reconcile",
    "triage",
    "cleanup",
    "adjudicate",
    "validate",
    "translate",
    "multi_translate",
    "refine",
    "typeset",
)

__all__ = ["__version__", "STEPS"]
