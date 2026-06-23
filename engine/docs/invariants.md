# Engine Invariants — the audit denominator

A *findings*-driven review has no denominator: "I found four issues" can't tell you whether you
stopped early or stopped right, and four-or-five is a suspiciously report-shaped number. This file
makes the unit of audit the **invariant**, not the finding. The invariants below are the closed,
enumerable set the engine must preserve for its conclusions to hold. An audit *runs the catalog*;
its result is a coverage map (which invariants' controls ran, which didn't), not a tidy list.

This does not abolish satisficing — it lifts it one level, from "did I find every bug?" (unbounded,
unreviewable) to "is this invariant list complete?" (bounded, and you can argue it is not). That is
the point: a missing invariant in a listed catalog is reviewable in a way a missing bug in an essay
is not. Extend the catalog when a new conclusion-bearing property is found; never prune a control to
go green (`feedback/no-cheating-results`).

## Standing audit prompt

> Run a coverage-driven audit, not a findings-driven review. First enumerate the invariants this
> pipeline must preserve for its conclusions to be valid. Then audit each invariant with source
> inspection and, where practical, one positive and one negative control. Do not stop because you
> have found a report-shaped number of issues. Report unchecked invariants, unrun probes, and
> residual risks separately from findings.

## How each invariant is specified

- **Conclusion underwritten** — the project claim that becomes false if the invariant breaks. This
  is *why* it is an invariant and not a preference.
- **Positive control** — evidence it holds on the real, valid case.
- **Negative control** — evidence the guard *fires* when the invariant is violated. A positive
  control alone is a happy-path fixture; without the failure branch the guard can rot to a vacuous
  pass (`feedback/single-fixture-blind-spots`, `feedback/validate-bindings`). "Where practical": some
  negative controls are documented probes, not automated tests — said so explicitly, never hidden.
- **Residual risk** — what the controls do *not* cover. Disclosed, not papered over.

## Catalog

### I1 — Config contract-completeness
Every field or asset a consumer dereferences is guaranteed by config-load validation (schema:
`required` + typed + non-empty/`minItems`/`contains`) or by a typed precondition at point of use; a
misconfiguration fails as `ConfigError` or a typed `EngineError`, never a late bare traceback.
- **Conclusion underwritten:** a schema-valid config is safe to run — config mistakes are clean exits, not crashes.
- **Positive:** `test_config_loader` (real profiles load); `test_assets::test_frequency_dictionary_resolves_to_a_file` / `test_period_dictionaries_resolve_to_dirs` (the real book's assets resolve).
- **Negative:** `test_config_loader` (each missing/empty required field → `ConfigError`: `prompt_context` keys, ≥1 monolingual period dict); `test_assets::test_require_asset_missing_*` / `test_require_asset_kind_mismatch_*` (a missing/typo'd asset → typed `MissingInputError` code 3, via `paths.require_asset`).
- **Residual risk:** asset existence is enforced at *step use*, not config-load (parallels how a missing spaCy model surfaces at use) — a typo is caught at the first step that needs the asset, not at `load_book`. The richer per-field override deep-merge is unbuilt (no consumer; `loader.py`).

### I2 — Failure-taxonomy completeness (F7)
Every *expected* failure raises a typed `EngineError` carrying its CLI exit code; only genuine
bug-class conditions reach a traceback.
- **Conclusion underwritten:** a known failure mode gives the user a clean message + stable exit code, not a stack trace.
- **Positive:** `errors.py` + CLI mapping (`ConfigError`/`UnknownLanguageError`→1, `NotImplementedError`→2, `EngineError`→its code).
- **Negative:** `test_download_engine` (network/HTTP → `AcquisitionError`); `test_ocr_engine` (unreadable PDF at page-count → `BackendError`; per-page render failure → `[OCR_ERROR]` sentinel, run continues); `test_assets` (missing asset → `MissingInputError`).
- **Residual risk (documented decision, not a hole):** the eight `read_json`/`["key"]` reads of engine-*internal* artifacts (`ocr` page files, `reconcile` page maps, `validate`/`adjudicate` inputs) intentionally remain bug-class. They are written by sibling steps **atomically** (`atomic_write_json`/`atomic_write_text`, now *enforced* by **I8**), so a present-but-corrupt artifact implies filesystem corruption or a writer bug — a traceback is the correct F7 response. (The post-M4a completeness audit found two text witnesses that bypassed this via raw `write_text`, briefly falsifying the assumption; F1 fixed them and I8 guards against regress. Revisit only for a hand-authored producer of any of these.)

### I3 — Port fidelity / divergence licensing
Deterministic steps reproduce the frozen-from-live goldens byte-for-byte; any change to a golden is
licensed by a divergence-ledger (`DL-NNN`) or input-refresh (`RF-NNN`) entry citing ground truth
(`port_discipline.md` §5 anti-cheat rule).
- **Conclusion underwritten:** the engine's deterministic output equals the live edition unless a divergence is explicitly, ground-truth-licensed — the whole forward-fork premise.
- **Positive:** `tests/golden/test_{chapterids,reconcile,validate}_golden` (frozen-fixture equivalence).
- **Negative:** golden comparisons are per-item `==` (non-vacuous by construction); `test_divergence_ledger` enforces the ledger stays machine-parseable and every entry is well-formed (ids sequential; a `DL` entry cites the `Golden:` it moves), with inline accept/reject fixtures giving it teeth while the real ledger is empty.
- **Scope (narrowed 2026-06-23):** the anti-cheat rule binds a golden change that alters expected **values** via a ground-truth-licensed behavioral change (→ `DL`) or a live-input re-freeze (→ `RF`). A pure report-envelope/format regeneration with **zero** behavioral diffs is exempt (commit-note only). The completeness audit's git-history probe found exactly one post-creation golden edit — `validation_report_expected.json` @ `93b5aa7`, an envelope regen with 0 classification diffs — which is **correct under the narrowed rule**, not a violation.
- **Residual risk (documented probe, not automatable):** detecting an *unlicensed re-baseline* — a golden whose **values** changed to launder a divergence without a `DL`/`RF` entry — needs human review (diff the fixture against git history + the ledger, judge whether ground truth licenses it). No unit test makes that judgement; run this probe by hand whenever a `*_expected` value changes.

### I4 — Core separability / neutrality
The engine package (`src/engine/`, including the language plugin) carries no book-identity or
typeface opinion. Which book, which entities, which typeface are config; the Italian plugin may carry
Italian-*language* opinion only.
- **Conclusion underwritten:** the engine ports to a second book by swapping `manifest`/`profiles`, with no source edit (the M7 extraction premise). (This is *neutrality of opinion*; the distinct safety property of *where writes land* is its own invariant, **I7**.)
- **Positive:** `test_acquisition_separability` (network/LLM seams are injectable, so the core logic holds no I/O opinion).
- **Negative:** `test_core_neutrality` — a forbidden-lexicon scan over all of `src/engine/` (code *and* prose) fails the moment a this-book / this-typeface term reappears. This is the standing form of the manual grep that caught "Bodoni" in three docstrings (c6790d6).
- **Residual risk:** the lexicon is a denylist of known-leak terms, not a completeness proof. Semantic leakage with no tell-tale term — a hardcoded chapter count, an Italian-only branch — is caught by config-extraction review (M7), not this scan. A new book/typeface term must be added to `FORBIDDEN`.

### I5 — Wire-protocol single-sourcing
Cross-step markers and sentinels (`⟨PAGE:N⟩`, `[BLANK]`, `[OCR_ERROR…]`) have exactly one definition
(`contracts/markers.py`); every consumer derives from it and never re-spells the literal.
- **Conclusion underwritten:** `ocr`'s emit format and `reconcile`'s parse regex cannot drift to different spellings (plan F6).
- **Positive:** `test_markers` (regex round-trips the template; regex is *derived*, not a second literal; sentinels pinned).
- **Negative:** `test_markers::test_wire_literals_are_single_sourced_across_the_package` — an AST scan of the whole package flags any executable string literal that re-spells a wire token outside `markers.py` (docstring/comment mentions excluded, since documentation is not a drift risk).
- **Residual risk:** the scan covers the three current wire tokens; a future protocol token must be added to `_WIRE_LITERALS` when it is introduced.

### I6 — Governance ↔ code consistency
The decision record (divergence ledger, branch register, this file, `port_discipline.md`) matches the
committed code: no stale counts, scrubbed terms, or dangling test references.
- **Conclusion underwritten:** the governance docs are trustworthy enough to reason from without re-reading all the code.
- **Positive / Negative:** partly mechanized — I3 keeps the ledger coherent; I4 keeps scrubbed terms out of core; referenced test names can be checked to resolve.
- **Residual risk (documented probe):** most of I6 is human cross-check performed at each milestone close (the post-M4a audit was one). Mechanizing "every doc claim still matches code" is open; until then it is an explicit per-milestone probe, not a test.

### I7 — Workspace write-containment (the safety property)
Every step writes only inside `books/<id>/work/`; no step can reach the parent repo's live trees
(`data/`, `output/`, `state/`, `docs/`, `static/`). Promoted out of I4 (2026-06-23): *where writes
land* is a distinct, higher-stakes property than *what opinion the code carries*.
- **Conclusion underwritten:** the engine can never overwrite the irreproducible live edition — the precondition for running it at all alongside the live tree.
- **Positive:** `BookWorkspace.resolve` rejects `..`/absolute escapes (`test_workspace`).
- **Negative:** `test_isolation` snapshots all five live trees before/after a real `run` of every ported step and asserts none changed — proof each step *uses* the guard, not just that the guard exists.
- **Residual risk:** read-only inputs (the scan PDF in `books/<id>/scans/`) sit outside the write-sandbox by design; containment guards writes, so a step that only reads there is fine, but the sandbox does not itself prevent a future step from *reading* an unexpected path.

### I8 — Atomic / no-partial-output
Every artifact a later step consumes is written through an atomic helper (`atomic_write_json` /
`atomic_write_text`: temp file + `os.replace`), never a raw write that a mid-write crash could
truncate into a file the next step reads as complete.
- **Conclusion underwritten:** I2's "a present internal artifact is never half-written, so a read failure is bug-class" — the justification for *not* wrapping the eight internal-JSON reads.
- **Positive:** `test_atomic_writes` — `atomic_write_text` round-trips and leaves no temp residue.
- **Negative:** `test_atomic_writes::test_atomic_write_text_failure_leaves_nothing_partial` (a forced mid-write failure leaves no destination file + no temp); `test_no_raw_artifact_writes_in_steps` (an AST scan forbids `.write_text`/`.write_bytes`/`open(...,'w')` anywhere under `steps/`).
- **Residual risk:** `os.replace` is atomic on POSIX; on some Windows filesystems it is not. The engine targets POSIX (no Windows CI) — documented, not active.
- **History:** found violated in the post-M4a audit (`download.py`/`ocr.py` raw `write_text` to consumed witnesses); fixed (F1) and now guarded.

### I9 — Determinism / idempotency
The deterministic steps (`reconcile`, `adjudicate`, `validate`, and `lang/italian.py` chapter-identity)
produce byte-identical output across runs, independent of `PYTHONHASHSEED` — distinct from I3: a step
can match its golden once yet be hash-order-nondeterministic, so a later regeneration silently flips it.
- **Conclusion underwritten:** the frozen goldens are stable and meaningful; a regeneration reproduces them.
- **Positive:** verified by source inspection (post-M4a audit) — every set/dict value reaching written output is `sorted()` or membership-only; module-level constant dicts; no `time`/`random`/`uuid`. Partially guarded already: a hash-order-nondeterministic output would intermittently break the I3 goldens.
- **Negative (NOT YET BUILT — listed, not claimed):** a run-twice-under-different-`PYTHONHASHSEED` idempotency test asserting identical output. Currently holds by inspection only.
- **Residual risk:** until the run-twice test exists, a future unsorted-set-to-output write is caught only by inspection or a flaky golden, not reliably.

### I10 — Config honesty
Every field declared in a schema and parsed into a model has a real consumer, or is a documented
reservation naming the milestone that will consume it — no silently dead config.
- **Conclusion underwritten:** the config surface is trustworthy; a field that exists does something (or is openly held for a named future step).
- **Positive:** the consumed fields trace to a reader (`cfg.…` access in a step/lang/helper).
- **Negative:** the post-M4a audit's field→consumer scan. It confirmed the forward-reserved fields map to named milestones (Edition/typeface → M3b; `substitution_rules`/`page_marker_format` → M4b; `oracle_min` → M6) and found one genuinely dead field, `spacy_distribution` (only a round-trip assertion referenced it) — **removed** (F3).
- **Residual risk:** "reserved vs dead" is currently a human judgement at audit time; there is no machine marker distinguishing a forward-reserved field from a dead one. A lightweight convention (a `$comment` naming the consuming milestone) would mechanize it — deferred (no second offender yet).

## Stop rule

An audit is complete when **every invariant's controls have been run or its unrun probes explicitly
listed** — not when a satisfying number of findings has accumulated. State the reason for stopping:
*controls exhausted*, *blocked on an unresolved finding*, or *intentionally bounded* (and say what was
left). "No fifth finding" is never itself a stop condition.

## Audit report shape

Report these four buckets **separately** — collapsing them is how a coverage gap masquerades as a
clean bill:

1. **Findings** — invariants whose controls failed (with the violating evidence).
2. **Unchecked invariants** — catalog entries whose controls were not run this pass, and why.
3. **Unrun probes** — documented probes (e.g. I3 unlicensed-rebaseline, I6 doc-consistency) not executed.
4. **Residual risks** — what the controls structurally do not cover, carried forward.

## Audit log

Append one line per audit: date — scope — invariants run — result (findings / coverage / stop reason).

- 2026-06-23 — post-M4a deep audit + invariant catalog stood up. Re-cast four ad-hoc findings as
  invariant controls: I1 (asset failure-branch → typed `MissingInputError`), I3 (ledger coherence),
  I4 (core-neutrality prose scan), I5 (cross-module wire-literal scan). One genuine code gap fixed
  (I1 asset precondition); the M4a taxonomy-agent's eight internal-JSON sites judged bug-class and
  left as tracebacks by design (I2 residual). Stop reason: controls exhausted for I1/I3/I4/I5; I2
  decision recorded; I6 remains a per-milestone manual probe.
- 2026-06-23 — catalog **completeness** pass (attack the denominator, not re-scan I1–I5). Found four
  unnamed invariants: I7 (containment, promoted from an I4 sub-bullet), I8 (atomic-write — **violated**
  at `download.py`/`ocr.py`, fixed F1 + new control), I9 (determinism — holds by inspection, control
  not yet built), I10 (config honesty — `spacy_distribution` dead, removed F3). Ran the deferred
  probes: I3 git-history (one envelope-regen golden edit @ `93b5aa7`, exempt under the **narrowed**
  anti-cheat rule — F2); I6 doc-refs (all catalog test names resolve). DL-001 declined. Stop reason:
  completeness controls exhausted; cadence returns to per-milestone (M4b) — no further immediate loop.
