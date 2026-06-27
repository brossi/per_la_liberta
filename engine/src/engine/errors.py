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


class RoundTripError(EngineError):
    """An L1 atom's raw/normalized round-trip floor failed (``structure.roundtrip``; §9, D22).

    Distinct from the operational step failures above: this is an *integrity* violation, not a
    missing input or a backend fault. Raised when the byte-exact raw tier fails — an out-of-bounds
    ``raw_span`` or a slice whose hash does not match ``raw_source_hash`` (the source artifact
    drifted, or the span is wrong) — or when the normalized tier fails (the declared transforms do
    not produce the stored text, or their inverses do not recover the raw). The floor a ``norm_layer``
    label cannot fake; failing it loud is the point.
    """

    exit_code = 7


class CaptureError(EngineError):
    """An L1 atom *stream*'s capture-completeness or span topology is violated (``structure.capture``;
    S1.3a, §3.0/§9).

    A stream-level integrity violation, the complement of :class:`RoundTripError`'s per-atom check:
    raised when a witness's atoms do not *tile* their source — a span out of bounds, an
    overlap/out-of-order span, or an uncovered non-whitespace gap (a *silent loss*: source bytes
    captured into no atom, the failure mode "everything is brought in" exists to forbid). The
    captured-but-excluded vs never-captured distinction is what makes this checkable (§3.0).
    """

    exit_code = 8
