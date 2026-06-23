"""Engine exception taxonomy → CLI exit codes.

One type per concrete failure an engine step can raise, each carrying the non-zero
``exit_code`` the CLI returns so a known failure is a clean message + code, not a traceback.
Deliberately minimal (F7): a category is added only when a real raiser exists — not pre-populated
"for completeness" (YAGNI). Exit codes ``1`` (config) and ``2`` (unported stub) are owned by the
CLI; the step failures below start at ``3``.

Current raisers (M4a):
  - ``MissingInputError`` — ``reconcile`` (OCR copies absent) / ``ocr`` (source scan PDF absent) /
    a config-referenced asset that does not resolve (``paths.require_asset``);
  - ``AcquisitionError`` — ``download`` network/HTTP failure;
  - ``BackendError``     — ``ocr`` rendering or transcription backend failure (an unreadable scan
    PDF at page-count, the vision-model call, or a missing key).
"""

from __future__ import annotations


class EngineError(Exception):
    """Base for engine failures the CLI maps to a clean exit code."""

    exit_code = 1


class MissingInputError(EngineError):
    """A step's required input artifact — or a config-referenced asset — is absent.

    Covers an absent workspace input (``reconcile``'s OCR copies, ``ocr``'s scan PDF) and a
    referenced asset that does not resolve (``validate``'s frequency dictionary, ``adjudicate``'s
    period-dictionary dir — via ``paths.require_asset``). Both are known, user-facing failures,
    so they exit cleanly (code 3) instead of as a bare ``FileNotFoundError`` traceback.
    """

    exit_code = 3


class AcquisitionError(EngineError):
    """``download`` could not fetch a source (network / HTTP failure)."""

    exit_code = 4


class BackendError(EngineError):
    """``ocr``'s rendering or transcription backend failed (an unreadable scan PDF at page-count,
    the vision-model call, or a missing key). A *per-page* render failure does not raise — it
    degrades to an ``[OCR_ERROR]`` sentinel; this is the whole-document / transcription case."""

    exit_code = 5


class RegenerationGuardError(EngineError):
    """A step refused to overwrite an existing protectable output without an explicit override.

    ``cleanup`` (and, at M4c, ``translate``/``refine``) writes an artifact a human may have
    hand-tuned inside ``work/``; a silent re-run would clobber it. The guard refuses unless
    ``allow_regen=True`` (kwarg) or ``ENGINE_ALLOW_REGEN=1`` (env) is set — deliberate friction
    mirroring the live ``PER_LA_LIBERTA_ALLOW_REGEN`` escape (BR-012/M4b-D2). The override form is
    a kwarg + env, no CLI flag; the error message names the escape for discoverability.
    """

    exit_code = 6
