"""S1.3b — typed projection over the raw atoms (ENGINE_STRUCTURE_PLAN §2-A; R3/D5, §9).

Concern A's second behavior. S1.3a captures a raw witness into a flat, source-ordered, addressed
atom stream; this module *types* that stream via an injectable ``BlockClassifier`` (the S0.4 seam →
the S9 recognizer), producing a flat **typed** stream. Each :class:`TypedAtom` pairs one immutable
:class:`~engine.structure.atoms.Atom` with the classifier's
:class:`~engine.structure.classify.BlockClassification` — its ``block_class``, the ``typed_by``
provenance, and the ``confidence`` B weighs when it re-types. Typing is the book-specific,
*correctable* step (R3/D5): B may re-atomize and re-type, not merely re-group, so every typed atom
records **who** typed it, never an anonymous label.

**Profile-scoped completeness (§9 — "never a degenerate green").** ``unknown``
(:data:`~engine.structure.classify.UNKNOWN`) is the engine's first-class *incomplete* state, not a
real class. Only **processed** atoms are in scope — those **not** ``processing_scope``-excluded:
furniture and wrappers are captured-with-role and *excluded* downstream (§3.0), so an excluded atom
left ``unknown`` is out of scope — never routed to review, never a hard-fail. (The test is
``!= excluded``, not ``== included``, so an out-of-vocabulary scope stays in scope and fails loud
rather than vanishing.) Whether a *processed* ``unknown`` atom
is fatal is the profile's call, scoped by its declared ``boundary_classes`` set (S9.1; passed in as
**data**, never a literal here, so the core stays book-agnostic). The discriminator is the atom's L1
``capture_provenance_class`` — the structural slot the bytes were captured into — matched against
``boundary_classes``:

  - an ``unknown`` atom whose ``capture_provenance_class`` **is** a declared boundary class →
    **hard-fail** (:class:`~engine.errors.IncompleteTypingError`): a structurally load-bearing slot
    the typing could not resolve breaks the skeleton, so it must be loud, never routed quietly.
  - an ``unknown`` atom in a **body leaf** (capture class not in ``boundary_classes``) → **route to
    review**: recorded with count + location in the returned :class:`CompletenessReport`, not
    raised. A partial result whose structure-bearing atoms are all resolved is *reviewable*, not
    broken.
  - an **all-unknown** processed set → **hard-fail** regardless of boundary classes: a projection
    that resolved *nothing* is degenerate-incomplete (exactly the S0.4 stub's output), never a quiet
    green that "passed".

**The boundary hard-fail is a mechanism + a forward contract, not yet a real-input guarantee.** It
keys on ``capture_provenance_class``, the only per-atom axis *independent* of the typed
``block_class`` (an atom is never both ``block_class in boundary_classes`` **and**
``block_class == UNKNOWN``). But today's S1.3a capture tags every non-furniture line with one body
class (``capture_witness``'s ``body_class``, default ``"authorial"``) and forces every *named*
``classify_line`` result to ``processing_scope="excluded"`` — so no real capture stream yet carries
an *included* boundary class. Until S9 makes capture granular (tagging heading / footnote-call /
embedded-letter-boundary lines with their own included ``capture_provenance_class``, which requires
relaxing that capture.py coupling), a real boundary left ``unknown`` is captured as the body class
and **routes to review** rather than hard-failing — surfaced for a human, not silently passed. (This
"routes to review, not silent" holds *because* ``classify_line``'s contract is furniture-only, so a
heading stays a body atom and is reviewable. A binding that *mis-used* ``classify_line`` to tag a
heading would get it ``excluded`` and *then* silently exempt — the reason S9 must add an *included*
boundary capture class, not route boundaries through the furniture path.) A heading recognizer
already exists in the live tree (a ported regex); the branch is dead today by **capture-scope
choice**, not because nothing could identify a boundary. It is exercised here by synthetic fixtures
and is ready for the day capture supplies included boundary classes. (A profile declaring a real
block class literally named ``"unknown"`` would alias the sentinel — guarded at S9.1 profile-load,
where the full class vocabulary is visible, not here.)

The returned report **feeds a review / governance surface; the exact consumer is unsettled.** The
done-when names "the S6 truth-table machinery", but S6.2 computes behavioral *flags* for *resolved
L2 nodes* from L2 provenance, whereas ``to_review`` queues *unresolved L1 atoms* keyed on L1
``capture_provenance_class`` — a different layer/axis/lifecycle, so the S8.1-style HITL stale/repair
report is the likelier home. ``CompletenessReport`` is the minimal local shape that later wiring
subsumes; it does **not** wire into S6 (unbuilt) or anything else today.

Pure core: ``boundary_classes`` is profile data the caller supplies; no language / ordinal /
book-structure literal lives here (the S0.2 neutrality guard scans this file).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from engine.errors import IncompleteTypingError
from engine.structure.atoms import PROCESSING_SCOPE_EXCLUDED, Atom
from engine.structure.classify import UNKNOWN, BlockClassification, BlockClassifier


@dataclass(frozen=True, slots=True)
class TypedAtom:
    """One raw atom paired with its :class:`BlockClassification` (the S1.3b typed-stream element).

    ``atom`` is the immutable L1 capture unit; ``classification`` is what the ``BlockClassifier``
    assigned (``block_class`` + ``typed_by`` + ``confidence``). Kept as a *pair* rather than fields
    spliced onto the atom because typing is a separate, **re-runnable** projection (R3/D5): B
    produces a *new* classification, it does not mutate the frozen atom. Frozen for the same reason.
    """

    atom: Atom
    classification: BlockClassification


@dataclass(frozen=True, slots=True)
class ReviewItem:
    """One body-leaf atom the typing left ``unknown`` — routed to review, not fatal.

    Carries the location a reviewer needs to find it: the ``atom_id`` (L1 identity), its raw
    codepoint ``raw_span``, its ``page_range``, and the ``capture_provenance_class`` that placed it
    in the body (and so off the hard-fail path).
    """

    atom_id: str
    raw_span: tuple[int, int]
    page_range: tuple[int, int]
    capture_provenance_class: str


@dataclass(frozen=True, slots=True)
class CompletenessReport:
    """The **non-fatal** outcome of :func:`check_completeness`.

    Returned only when the projection's structure-bearing (boundary-class) atoms are all resolved
    **and** at least one *processed* atom is resolved — the fatal cases (a boundary-class atom
    ``unknown``, or an all-``unknown`` degenerate projection) do not return a report, they raise
    :class:`~engine.errors.IncompleteTypingError`. ``to_review`` lists the body-leaf atoms still
    ``unknown`` (the count + location S1.3b routes to review); ``processed_count`` is the number of
    **processed** (``processing_scope``-included) atoms the check ranged over — excluded furniture is
    out of scope and not counted (§3.0). ``is_complete`` is the only-green state: nothing to review.
    """

    to_review: tuple[ReviewItem, ...]
    processed_count: int

    @property
    def is_complete(self) -> bool:
        """``True`` iff no atom needs review — the projection is fully typed."""
        return not self.to_review

    @property
    def review_count(self) -> int:
        """How many body-leaf atoms were routed to review."""
        return len(self.to_review)


def typed_projection(
    atoms: Sequence[Atom],
    classifier: BlockClassifier,
) -> list[TypedAtom]:
    """Type a raw atom stream into a flat, source-ordered typed stream (S1.3a → S1.3b).

    Runs ``classifier.classify(atoms)`` and zips each atom with its classification, preserving
    source order. The S0.4 seam contract is *positional correspondence* — one classification per
    atom, same order — so a classifier returning the wrong count is a broken contract and raises
    :class:`ValueError` rather than silently zipping to the shorter length (which would drop the
    tail of either stream unnoticed). The atoms themselves are untouched; typing is a projection.
    """
    classifications = list(classifier.classify(atoms))
    if len(classifications) != len(atoms):
        raise ValueError(
            f"classifier {type(classifier).__name__!r} returned {len(classifications)} "
            f"classifications for {len(atoms)} atoms — the BlockClassifier seam contract is one "
            f"classification per atom, positionally aligned (S0.4); a mismatch would silently drop "
            f"the tail of the longer stream."
        )
    return [TypedAtom(atom=a, classification=c) for a, c in zip(atoms, classifications)]


def check_completeness(
    typed: Sequence[TypedAtom],
    *,
    boundary_classes: Iterable[str],
) -> CompletenessReport:
    """Assert the profile-scoped typing-completeness of a typed projection (§9; S1.3b).

    ``boundary_classes`` is the profile-declared set of ``capture_provenance_class`` values that
    are structurally load-bearing (S9.1); a bare ``str`` is rejected (it would iterate to a
    character set). Only **processed** atoms are in scope — those *not* ``processing_scope``-excluded:
    furniture/wrappers are captured-with-role and excluded downstream (§3.0), so an excluded atom
    left ``unknown`` is *not* an incompleteness — it is never routed to review and never a hard-fail.
    An out-of-vocabulary scope stays in scope (``!= excluded``), failing loud rather than vanishing.
    Over the processed atoms: raises
    :class:`~engine.errors.IncompleteTypingError` when they are **all-unknown** (degenerate —
    resolved nothing) or when any **boundary-class** atom is ``unknown``; otherwise returns a
    :class:`CompletenessReport` listing the body-leaf ``unknown`` atoms routed to review (count +
    location). An empty projection — or an all-excluded one — is vacuously complete: typing-
    completeness has nothing to resolve, and capture-emptiness is S1.3a/S1.4's concern, not this one.
    """
    if isinstance(boundary_classes, str):
        # A bare str is a valid Iterable[str] but iterates its *characters* — `frozenset("heading")`
        # is {'h','e',…}, so a multi-char class could never match and the boundary hard-fail would
        # silently downgrade to route-to-review (a severity inversion). Reject it loudly.
        raise TypeError(
            f"boundary_classes must be a set/collection of class names, not a bare str "
            f"({boundary_classes!r}); pass {{'heading'}}, not 'heading'."
        )
    boundary = frozenset(boundary_classes)
    # Scope to the processable structure (see docstring): excluded furniture is exempt. The test is
    # `!= excluded` (excluded is the *explicit* opt-out, §3.0), not `== included`, so an
    # out-of-vocabulary `processing_scope` (a typo, a future third value) stays **in scope** and is
    # caught by the degenerate/boundary checks rather than silently dropped — silently dropping it
    # would reopen the "all-unknown passes green" hole this check exists to close. Filtered here, not
    # in `typed_projection`, so the typed stream stays complete ("everything is brought in").
    processed = [t for t in typed if t.atom.processing_scope != PROCESSING_SCOPE_EXCLUDED]
    total = len(processed)
    unknown = [t for t in processed if t.classification.block_class == UNKNOWN]

    # Degenerate: a non-empty processed set that resolved *nothing*. Checked first because its root
    # cause (a stub or wholesale-misconfigured classifier) is distinct from, and more fundamental
    # than, a few specific boundary slots failing — so it earns its own diagnosis.
    if total and len(unknown) == total:
        raise IncompleteTypingError(
            f"typed projection is degenerate: all {total} processed atom(s) are {UNKNOWN!r} — the "
            f"classifier resolved nothing (the S0.4 stub's output, or a misconfigured recognizer). "
            f"An all-{UNKNOWN} projection fails completeness; it is never a quiet green (S1.3b, §9)."
        )

    boundary_unknown = [t for t in unknown if t.atom.capture_provenance_class in boundary]
    if boundary_unknown:
        locs = ", ".join(
            f"{t.atom.atom_id} (class {t.atom.capture_provenance_class!r}, span {t.atom.raw_span})"
            for t in boundary_unknown
        )
        raise IncompleteTypingError(
            f"{len(boundary_unknown)} boundary-class atom(s) typed {UNKNOWN!r} — a structurally "
            f"load-bearing slot the typing could not resolve must fail loud, not route to review. "
            f"Declared boundary_classes={sorted(boundary)!r}; offending atoms: {locs}."
        )

    to_review = tuple(
        ReviewItem(
            atom_id=t.atom.atom_id,
            raw_span=t.atom.raw_span,
            page_range=t.atom.page_range,
            capture_provenance_class=t.atom.capture_provenance_class,
        )
        for t in unknown
    )
    return CompletenessReport(to_review=to_review, processed_count=total)
