# Engine Structure — Task Decomposition & Development Tracker

Branch: `spike/document-structure`. Derives from the signed-off spec
**`ENGINE_STRUCTURE_PLAN.md`** (design ratified 2026-06-26, D1–D35) and its provenance
archive `ENGINE_STRUCTURE_PLAN_DISCUSSION.md`. This file turns that spec into trackable
development work; it does **not** re-decide anything — where it and the plan disagree, the
plan wins, and the discrepancy is a bug in this file.

## How to read / track this

- The spec answers *what & why*; this file answers *what to build, in what order, done
  when*. Every task cites the spec section and decision(s) it discharges (`§3.4`, `D33`),
  so a task that drifts from the spec is visible.
- **Status** is tracked in the `St` column of each milestone table and rolled up in the
  Milestone map. A milestone rolls up `DONE` when **all its non-`DEFER` tasks are DONE**.
  Update the cell when a task moves; keep the rollup in sync.
- Audits use the house workflow: drop a `@@@@@@` block under **§ Audit log**, answer with a
  paired `======` (code-verified, per point); once resolved, fold the outcome into the
  affected task **and** the relevant spec section, then strike the thread.
- Code anchors are `path · symbol` / `path:line` and were verified against the **engine
  tree** (`engine/src/engine/`) on the branch as of authoring; re-confirm before editing
  (line numbers drift). **Live-PLL evidence anchors** — cited as design evidence, not engine
  code to edit — are prefixed **`[live]`** and resolve in the *root* repo, not `engine/`.

## Conventions

**Task ids** — `S{milestone}.{task}` (e.g. `S4.2`). Milestones are `S0`–`S10`. Tasks added
after first authoring keep a stable id (e.g. `S2.0`, `S7.3a/b`) rather than renumbering.

**Status legend** (`St`):

| Mark | Meaning |
|---|---|
| `TODO` | not started |
| `WIP` | in progress |
| `DONE` | merged + tests green on branch |
| `DEFER` | deliberately not built now (carries a revisit condition) |
| `BLOCK` | blocked on an unmet dependency |

**Scope tags** (from §6 / D31 — the build-enough discipline). *Distinct from `St`:* a tag is
what kind of work it is; `St` is how far along. A `SEAM` task is still built now.

| Tag | Meaning |
|---|---|
| `BUILD` | general mechanism **and** PLL-v2 instance, both now |
| `SEAM` | general mechanism now, **unpopulated** for PLL (a reserved hook) |
| `DEFER` | genuinely-unsolved; reserved hook only, no instance (overlap, D32) |
| `GATE` | an acceptance gate — downstream work is not "born" until it is green |
| `SCAF` | scaffolding / harness / probe, no shipped behavior |

**Test tiers** (house tiers, `uv run --directory engine pytest`; §9 of the spec):
`property` · `neutrality` · `golden` (I3 anti-cheat: expected values come from the live
implementation) · `reference-integrity` · `round-trip` (raw byte-exact + normalized
reversible) · `re-binding` · `space-recon` · `scale` · `negative` (fail-loud, no
skip-masking).

## Orientation — what the axis builds

Three concerns, non-linear (spec §2); a three-layer substrate (spec §3.2):

```
A. block extraction   → L1 immutable addressed atoms        (identity = atom_id)
B. structural assign.  → L2 versioned block projections       (identity = node_id)   ← runs first (D29)
C. relations           → L3 spans / fields / relations / align (typed endpoint union)
```

This substrate is in scope **because the engine is the production pipeline for a
re-translated PLL v2 (D28)** — a real build target, which is what makes the B/C governance
milestone (S8) necessary rather than speculative.

The **build / seam / defer** split this tracker implements, lifted from §6:

- **BUILD (PLL v2 instance):** ragged container tree (depth discovered); a **typed,
  correctable** block stream (A types via the book's block-classifier; **B can re-atomize /
  re-type, not merely re-group** — R3/D5); L2 `paragraph` + `verse` + the embedded-letter
  container; L1 geometry + Zipf-DP space reconstruction; opaque `node_id` + `rebind_anchors`
  + alias records; `position-path` + `ordinal-word` handle policies; block-level
  span-capable cross-language alignment; heterogeneous children; the three status axes +
  derived flags; lineage manifest + stale-fail governance; the second-structure fixture
  (D18); a scale check for the unbounded-unit-count design (D35).
- **SEAM (mechanism, no PLL instance):** depth-from-designation deriver (Tractatus);
  graph cross-ref edge type (Britannica dangling refs); per-node/per-span authorship
  beyond PLL's few overrides; block vocabulary beyond `paragraph`/`verse`.
- **DEFER (genuinely unsolved):** overlapping / interleaved hierarchy — the reserved
  `participates-in` L3 hook only (D15/D32), no instance.

---

## Milestone map

| # | Milestone | Concern | Gate(s) | St (rollup) |
|---|---|---|---|---|
| S0 | Scaffolding & test spine | — | neutrality | `TODO` |
| S1 | L1 atom substrate | A | raw round-trip floor | `TODO` |
| S2 | Geometry capture (D30) | A | **bbox probe (S2.0)** | `TODO` |
| S3 | Space / fragment reconstruction (D30) | A | corruption guard | `TODO` |
| S4 | L2 projections + `node_id` + structure map | B | **D18 second-structure fixture (S4.5)** | `TODO` |
| S5 | Re-binding (D33) | B | rebind fail-loud + regen-guard | `TODO` |
| S6 | Read-fields & status axes | B | — | `TODO` |
| S7 | L3 + relations + cross-language alignment | C | — | `TODO` |
| S8 | Governance & lifecycle spine | B/C | negative battery | `TODO` |
| S9 | Recognition: profile + code escape | — | neutrality | `TODO` |
| S10 | Integration & migration (F2/F3/F4) | — | PLL golden (no regression) | `TODO` |
| S11 | Post-build evaluation (academic v1↔v2) | — | none — diagnostic, **not** a gate | `TODO` |

## Dependency graph

```
S0
 └─ S1 ─┬─ S1.1 freezes the geom field SHAPE  ──►  S4 schema   (S4 needs S1.1, NOT S2)
        │
        ├─ S2.0 bbox PROBE (GATE) ─► S2 geom ─┬─► S3 space-recon
        │                                     └─► S5 rebind ◄─ S4.5
        │
        └─ S4 schema ─► S4.5 D18 FIXTURE (GATE) ─► S5 · S6 · S7 · S8 · S9 · S10
                        S4.6 PLL map (human: Ben) · S4.7 scale test  ◄─ S4.1/S4.2

 Gate rule:  no B/C task (S5–S8, S10) reaches DONE until S4.5 is green — so every such
             task lists S4.5 (not an S4 sub-task) as its upstream.
 S8.1 (governance loader) is pulled EARLY — it is upstream of S5.2 (rebind fail-loud needs
       the regen-guard); S8.2/S8.3 stay downstream of S5/S7.
 S2.0 is pulled EARLY — a negative outcome reroutes S2 to the word-coordinate fallback
       BEFORE S2/S3/S5 build on a bbox layer that may not exist.
```

- **S4 is the keystone; S4.5 (D18) is its birth gate.** S4's *schema* needs S1 (atoms) +
  the `geom` field shape, which **S1.1 freezes** — so S4 does **not** wait on S2's
  extraction backend. Geometry *extraction* (S2) and space reconstruction (S3) are a
  parallel pole feeding the PLL **instance** and re-binding (S5), not the schema.
- **The gate binds by dependency** — every B/C task names **S4.5** upstream, so nothing is
  marked DONE against an unborn schema.
- **S5 needs both S2 and S4.5** (geometry is the primary re-bind signal; the map stores the
  anchors).

### Critical path

`S0 → S1 → S4 → S4.5 (D18 GATE) → {S5 → S8.2/S8.3}` for the substrate; `S0 → S1 → S4 →
S10.4 (PLL golden)` for the integration payoff. The geometry pole `S2.0 → S2 → {S3, S5}`
runs in parallel and rejoins at S5. The long poles are **S4** (keystone + gate) and **S9**
(relocating recognition off the live cycle-breaker `chapter_identities`).

### Waves (what can run together)

- **W0:** S0
- **W1:** S1, **S2.0** (bbox probe — needs only the PLL PDF; gates S2)
- **W2:** S2 (after S2.0 green), S4 schema (S4.1–S4.4, after S1)
- **W3:** S3, **S4.5 (D18 gate)**, S4.6 (human map), S4.7 (scale), **S8.1** (governance loader)
- **W4:** S5, S6, S7, S9 (all after S4.5 green)
- **W5:** S8.2, S8.3, S10
- **W6:** S11 (only once a full v2 extraction run exists — academic, off the critical path)

---

## Tasks

### S0 — Scaffolding & test spine `SCAF`

Stand the package up before any behavior, with the neutrality guard live from commit one.

| ID | Deliverable | Refs | Deps | Done-when (tier) | Tag | St |
|---|---|---|---|---|---|---|
| S0.1 | `engine/src/engine/structure/` package skeleton; schema-version constants; artifact locations fixed under `books/<id>/work/` (`atoms/`, `structure_map.json`, `relations.json`) | §3, §11 | — | package imports; constants asserted | `SCAF` | `TODO` |
| S0.2 | Neutrality guard `test_structure_neutrality`: core `structure/` carries no language/ordinal/structure literal (no `Capitolo`, no `«»`, no part-count) | §9, `feedback_engine_agnostic` | S0.1 | guard fails on a planted literal; green on the package | `GATE` | `TODO` |
| S0.3 | Test-tier harness stubs (property / golden / negative) wired into `uv run --directory engine pytest`; golden generator reusing the existing `engine/tests/golden/_generate_*_fixture.py` pattern | §9 | S0.1 | tiers collect + run; a generator round-trips a trivial fixture | `SCAF` | `TODO` |

### S1 — L1 atom substrate (concern A) `BUILD`

Immutable, addressed capture units — the floor everything pins to.

| ID | Deliverable | Refs | Deps | Done-when (tier) | Tag | St |
|---|---|---|---|---|---|---|
| S1.1 | L1 `Atom` model: `atom_id`, `witness`, `text`, `raw_span`, `raw_source_hash`, `page_range`, `norm_layer`, **`geom` slot (field shape frozen here)**, `provenance_class`, `derived_from`. Pure core dataclass, no language opinion | §3.0, §3.2, §11.1; D10, D20 | S0 | property: ids unique, immutability holds; `geom` shape is fixed (S2/S4 depend on it) | `BUILD` | `TODO` |
| S1.2 | **Two-tier no-loss round-trip:** (a) raw byte-exact reconstruction from `raw_span` + `raw_source_hash` for every captured atom; (b) normalized = raw ⊕ declared reversible transforms. `norm_layer` is a label, never the guarantee | §3.0, §9; D22 | S1.1 | round-trip tier (a) byte-exact; (b) transform-reversible | `GATE` | `TODO` |
| S1.3 | Atom-stream **construction**: re-segment `copy{1,2,3}_raw.txt` into per-witness atom streams **+** one canonical reconciled projection (`derived_from` back-links). A emits **typed** atoms via the book's block-classifier (typing is book-specific, R3). `provenance_class` + `processing_scope` carry furniture (captured-but-excluded ≠ never-captured) | §2-A, §3.0; multi-witness fact `reconcile.py:553–562 / :630–673 / :716 / :485`; D5/R3, D25 | S1.1 | property: every canonical atom has ≥1 witness derivation; atoms carry a block-type; furniture captured-with-role | `BUILD` | `TODO` |

> **S1.3 is not a read-only re-projection.** reconcile segments copy1/2/3 in memory and
> **discards** the per-witness structural streams (§1 multi-witness fact), persisting only
> the merged `reconciled_chapters.json` + word-flags. So per-witness atom streams must be
> **re-built** by re-running segmentation on the raw copies — specify that algorithm here;
> do not describe it as "read-only from reconcile." This is the F4 fix: each witness atom
> stays addressable, and the `(ch_id, para_idx)` disagreement flags become L3 spans in S7.

### S2 — Geometry capture, D30 (concern A) `BUILD`

| ID | Deliverable | Refs | Deps | Done-when (tier) | Tag | St |
|---|---|---|---|---|---|---|
| S2.0 | **bbox-availability PROBE (GATE).** Measure the OCR textpage/bbox layer on real PLL pages: does a usable word-box layer exist, and at what quality? A negative/low-quality outcome **reroutes S2.1 to the word-coordinate fallback** (explicit, not silent). Gates S2.1 / S3.1 / S5.1 | §3.0; D30; §1 portability note (`pll` PDF is an image scan) | S0.1 | a written probe result on ≥10 PLL pages; the S2.1 path (textpage vs re-derive) is **chosen by evidence** | `GATE` | `TODO` |
| S2.1 | `GeometrySource` seam (Protocol) + backend on the **path S2.0 selected**: PyMuPDF/Fitz textpage/bbox layer, or word-coordinate re-derivation → `atom.geom` word-box union; canonical atom carries its primary witness's box | §3.0, §11.1; D30 | S1.1, S2.0 | seam injectable; backend yields boxes for a PLL page fixture | `BUILD` | `TODO` |
| S2.2 | Geometry property tests: boxes proven within page bounds; source-order ↔ geometric-order coherence on a real page; primary-witness box on canonical atoms | §9 | S2.1 | property: those three assertions hold | `BUILD` | `TODO` |

> **Risk (now gated, not just noted):** geometry presupposes a usable OCR bbox layer on the
> LOC PDF. S2.0 is the build-now probe that settles it before S2/S3/S5 commit; its negative
> branch is a real, scoped fallback, not an afterthought.

### S3 — Space / fragment reconstruction, D30 (concern A) `BUILD`

| ID | Deliverable | Refs | Deps | Done-when (tier) | Tag | St |
|---|---|---|---|---|---|---|
| S3.1 | Zipf-cost DP word-segmentation over `data/dictionaries/it_combined.txt` (`wordcost = -log prob`, DP + backtrack), **oracle-gated** by the ≥2-of-3 period dictionaries. Recovers split/merged spaces & fragments — **not** by inverting `collapse_spaces`/`rejoin_lines` | §2-A, §3.0; D30 | S2 (geom base layer), dict + oracle | property: known fragments re-segment | `BUILD` | `TODO` |
| S3.2 | Corruption-guard tests: a period-form the ≥2-of-3 oracle accepts is **not** "corrected" away; regression set drawn from `project_cleanup_corruption` | §9 space-recon; `project_cleanup_corruption` | S3.1 | space-recon tier green incl. the no-corruption negatives | `GATE` | `TODO` |

> **Risk:** modern-frequency cost can outvote a valid 1913 form. The oracle gate is the only
> thing between this step and re-running the cleanup-corruption mistake; S3.2 is a gate, not
> a nicety. *(S3's relationship to the PLL golden is **resolved**, § Audit log: S3 changes
> text by design, so it is validated by its own space-recon tier (S3.2) + the raw floor
> (S1.2) and feeds the v2 **instance**, never the no-regression golden (S10.4). The v1↔v2
> accuracy of S3's output is measured academically, post-build, by S11.)*

### S4 — L2 projections + `node_id` + structure map (concern B) — **keystone**

The durable catalogue. **S4.5 (D18) is the birth gate for the whole B/C substrate.**

| ID | Deliverable | Refs | Deps | Done-when (tier) | Tag | St |
|---|---|---|---|---|---|---|
| S4.1 | L2 projection model: container vs leaf; open per-book block vocabulary (PLL: `paragraph`, `verse`, embedded-letter container); **no-double-ownership** invariant; **B can re-atomize and re-type, not merely re-group** (the block-classifier output is correctable, R3/D5) | §3.1, §3.2, §11.2; D10, **D5/R3** | S1.1 | property: no atom owned twice; ragged depth 0–4 + recursion + **heterogeneous sibling classes** representable; a mis-typed atom is corrected by B (re-type) | `BUILD` | `TODO` |
| S4.2 | `node_id` identity + minting split: opaque, persisted, **never recomputed** from position/designation/content; humans mint containers, extractor machine-mints leaves (counter/ULID); `minted_by` field | §3.4; D11, D20, D33 | S4.1 | property: id stable across re-serialize **and after a positional move** (re-mint proves position-independence) | `BUILD` | `TODO` |
| S4.3 | Handle policy + rendered handles + alias records: per-node-class `handle_policy` (`position-path` \| `designation-string` \| `title` \| …) with inheritance; `(node_id, handle_policy)` renders `short`/`parse_md`/`html_slug`; alias record `{handle_type,value,scope,locale_or_witness,target_node_id,valid_from,valid_to,status}` | §3.4, §3.6; D12, D24, D33 | S4.2 | property: handle change leaves `node_id` fixed, old handle survives as alias | `BUILD` | `TODO` |
| S4.4 | `structure_map.json` **schema** + **lineage manifest** header (raw + atom-stream + canonical-projection hashes, `canonical_stream_id`, profile + recognizer versions) | §3.5, §3.6, §11.2; D21 | S4.1–S4.3, **S1.1 (geom shape)** | schema validates; reference-integrity tier (every ref resolves) | `BUILD` | `TODO` |
| S4.5 | **D18 GATE — second-structure synthetic fixture built to DIFFER from PLL:** depth-0 body (no parts), `designation-string` handle policy, alias-uniqueness-in-scope, stale-manifest failure, relation-endpoint resolution. **Distinct from the existing `books/synthetic`** (prefazione + 1 part, Italian ordinals, H2/H3 — a miniature PLL, *not* a differ-fixture) | §6 (last row), §9; D18; `feedback_single_fixture_blind_spots` | S4.1–S4.4 | the fixture passes; **schema is not "born" until it does** | `GATE` | `TODO` |
| S4.6 | **Hand-author the PLL container map** (~61 containers). **Owner: Ben (human-in-the-loop).** Code (S4.4) provides the schema; this is the human authoring deliverable, tracked separately so "code done / map pending" is an honest state | §3.5; D28/D29 (HITL premise) | S4.4 | the authored map validates against PLL's known skeleton (prefazione + 2 parts + 57 chapters + the embedded letter) | `BUILD` (human) | `TODO` |
| S4.7 | **Scale check (D35).** Property/benchmark over a synthetic tree at the design ceiling: structure ops, reference-integrity resolution, and re-bind stay **sub-quadratic** measured across sizes (e.g. 10⁴ → 10⁵ leaf nodes). The assertion is the *shape* (sub-quadratic growth), so the exact ceiling is not load-bearing | §3.5; **D35** | S4.1, S4.2 | scale tier: growth ratio confirms sub-quadratic; flat addressable storage holds at 10⁵ | `BUILD` | `TODO` |

> **S4.4 + S4.6 bootstrap order:** the hand-authored PLL map (S4.6) gives S5–S8 something
> real to chew on; S9 later makes that map *recognizer-suggested*. The existing
> `books/synthetic` is a pipeline fixture (copy1/2/3 → reconciled), **not** a structure-differ
> fixture — S4.5 builds a new one (a depth-0 / headword corpus, Kybalion- or Tractatus-shaped).
> **Design ceiling for S4.7 (proposed):** PLL ≈ 10³ leaf nodes; Pepys ≈ 10⁴ (2 901 day-entries
> × paragraphs); a full reference-work volume (Britannica-class) ≈ 10⁵ — so 10⁵ covers the
> largest plausible single-document witness, two orders above PLL. The test asserts
> sub-quadratic *shape*, so this number can move without reworking the task.

### S5 — Re-binding, D33 (concern B) `BUILD`

| ID | Deliverable | Refs | Deps | Done-when (tier) | Tag | St |
|---|---|---|---|---|---|---|
| S5.1 | `rebind_anchors` per node: **geometry region** (primary, from D30 word-boxes), **fuzzy/fail-loud content fingerprint** (never the exact-substring the live tree tombstoned), **structural-path** tie-break. Re-attach algorithm with an **explicit confidence threshold** — a named parameter defaulting toward **fail-loud on doubt**: unique + above-threshold → bind; else fail loud | §3.4, §3.6; D33, R2; `feedback_existing_path_failures_as_evidence` | S2, **S4.5** | re-binding tier: regenerated stream re-binds stored ids under unchanged geometry | `BUILD` | `TODO` |
| S5.2 | Re-binding negatives + **threshold calibration** + **regen-guard registration**: ambiguous / below-threshold re-bind raises into governance (assert the raise); a property test **measures the mis-bind rate on a perturbed atom stream** so the threshold is set by evidence; structure map joins the regeneration-guard family (one-way gate) | §3.4, §9; D33 | S5.1, **S8.1** | negative tier raises; mis-bind rate measured; regen-guard refuses silent regen of the map | `GATE` | `TODO` |

> **Risk:** the threshold is the dial between silent-misbind and noisy-fail. The live
> `corrections.json` 40-char anchor proved exact-substring matching fails on re-extraction;
> the fuzzy fingerprint **defaults to fail-loud on doubt** and the dial is **set by S5.2's
> measurement**, not by taste.

### S6 — Read-fields & status axes, §3.3 (concern B) `BUILD`

| ID | Deliverable | Refs | Deps | Done-when (tier) | Tag | St |
|---|---|---|---|---|---|---|
| S6.1 | Three **orthogonal** axes: `role` (`front\|body\|back`, structural matter only); `authorship` (scope `work\|witness\|translation\|span`, overridable — PLL's Mazzini-letter override); `provenance_class` (`authorial\|editorial\|translator-note\|transcriber\|generated-TOC\|scan-OCR-furniture\|source-wrapper\|renderer-added`). Designation ≠ title (both optional display fields) | §3.3; D13, D23 | **S4.5** | property: axes independent; no `excluded` smuggled into `role` | `BUILD` | `TODO` |
| S6.2 | Derived behavioral flags `translatable` / `alignable` / `counts_for_retention` / `rendered`, computed by policy from the axes; validators switch on **flags**, not on a `provenance_class` literal | §3.3; D23 | S6.1 | property: adding a `provenance_class` needs no validator edit | `BUILD` | `TODO` |

### S7 — L3 + relations + cross-language alignment, R5/D34 (concern C)

| ID | Deliverable | Refs | Deps | Done-when (tier) | Tag | St |
|---|---|---|---|---|---|---|
| S7.1 | `SpanRef = {atom_id,start,end}` + typed endpoint union (`atom_range \| projection_node \| span_ref`); L3 span/field model (speaker/date/author/citation; footnote = L2 note-body + L3 call-site span + `note-of` relation) | §3.2, §11.3; D19 | S1.1, **S4.5** | reference-integrity: every endpoint resolves | `BUILD` | `TODO` |
| S7.2 | **Cross-language alignment relation**, general source↔target (LANG_A↔LANG_B, **not** bespoke IT↔EN): many-to-many over `node_id`/`SpanRef`, per-edge `method` (`by-index\|by-content\|human`) + `confidence`, versioned `alignment_set`. A paragraph index is *one method*, never the durable key | §4 R5; D7, D34; `[live]` `typeset.py:609` mispoint evidence | **S4.5**, S7.1 | property: index-as-method, node-id-as-key; partial (span) align needs no schema change | `BUILD` (PLL: IT↔EN instance) | `TODO` |
| S7.3a | **Graph cross-ref edge type** (may dangle / resolve externally — Britannica): concern-C edge orthogonal to containment, with external/unresolved semantics. Mechanism now, no PLL instance | §6; D14 (C edges); R1 (EB) | S7.1 | property: an edge may dangle and is reported, not silently dropped | `SEAM` | `TODO` |
| S7.3b | **Reserved `participates-in` hook** (`contiguous:false`, typed members) for overlapping / interleaved hierarchy. Reserved only — no instance, Hamlet-conformance-checked | §6; D15, D32; R4 | S7.1 | the hook exists + is uninstantiated; Hamlet case documented as the trigger | `DEFER` | `DEFER` |

> S7.2 is the structural replacement for the shipped `[live] typeset.py:609` mispoint (EN
> paragraph *index* reused on the IT column; 23/58 chapters diverge → 14 mispoints). Cited as
> evidence only — fixing the live `typeset.py` is a separate live-PLL matter (deploy-hold,
> not this branch).

### S8 — Governance & lifecycle spine, §3.6 (concern B/C) `BUILD`

S8.1 (the loader) is pulled into W3 — it is a prerequisite of S5.2's fail-loud, not a
follow-on. S8.2/S8.3 stay downstream of the models they police.

| ID | Deliverable | Refs | Deps | Done-when (tier) | Tag | St |
|---|---|---|---|---|---|---|
| S8.1 | Stale = **fail-loud** loader keyed on the lineage manifest; *why-stale → which-migration* routing (raw OCR changed → re-capture; normalization changed → re-derive offsets; projection changed → re-attach L2/L3) | §3.6; D14, D21 | S4.4 | negative: a changed hashed input fails load until refresh/migrate | `BUILD` | `TODO` |
| S8.2 | Decision provenance per entry (`human-approved\|plugin-suggested\|inherited`; re-suggestion never overwrites a human ruling); **C-corrections are reviewer-approved patches** to L2/L3, never auto-rewrite of L1; L1 supersession-by-new-stream + tombstone (kept-marked-invalid) | §3.6; D14, D25 | S4.4, S5.1 | property: human ruling survives re-suggest; superseded atom ids stay addressable | `BUILD` | `TODO` |
| S8.3 | **Negative battery** (fail-loud, no skip-masking): alias collision in scope · unresolved relation endpoint · stale lineage manifest · ambiguous re-bind — each asserts the raise. Plus reference-integrity binding (every ref / endpoint / `status:active` alias resolves to exactly one node) | §9; `feedback_validate_bindings`, `feedback_no_cheating_results` | S4.5, S5, S7 | negative + reference-integrity tiers green; no `skipif` masking | `GATE` | `TODO` |

### S9 — Recognition: profile + code escape, §7.1 (D17/D27) — resolves BR-021

| ID | Deliverable | Refs | Deps | Done-when (tier) | Tag | St |
|---|---|---|---|---|---|---|
| S9.1 | Structure profile (`engine/profiles/structure/` + new `BookManifest.profile_refs["structure"]`): **data primitives only** — heading regexes, running heads, matter labels, designation grammar, numbering scope, block-split rules. No DSL, no control flow in JSON. **Mirror the existing `engine/profiles/{languages,source_noise,typefaces}` schema convention** | §7.1; D17, D27; `config/models.py · BookManifest:108` (`profile_refs:113`) | S4.5 | profile loads via the existing loader pattern; neutrality tier still green | `BUILD` | `TODO` |
| S9.2 | **Split recognition out of `LanguagePlugin`**: relocate the abstract structure surface — `is_chapter_heading` / `parse_chapter_number` / `structural_part` / `strip_boilerplate` / `split_raw_chapters` (`lang/base.py:42–78`) **and the ordinal/heading data tables** (`lang/italian.py:26–290` — `ORDINALS`:26 … `_PARTS`:134 + methods) — into the structure recognizer; narrow **code-escape** reader for irreducibly procedural cases (Hamlet turn-state); PLL = profile + relocated Italian reader | §7.1, F1; D8, D17, D27 | S9.1 | the abstract structure surface is **gone from `lang/base.py`** (asserted); the existing `engine/tests/golden/test_chapterids_golden.py` reproduces PLL identities unchanged; an Italian-free core recognizes the S4.5 differ-fixture | `BUILD` | `TODO` |
| S9.3 | **Depth-from-designation deriver seam** (Tractatus dotted-decimal → depth 0–6). Mechanism now, **unpopulated for PLL** (PLL uses `position-path`, no depth derivation) | §6; R1 (Tractatus) | S9.1, S4.3 | Tractatus-style designation computes depth via the seam; PLL path does not invoke it | `SEAM` | `TODO` |

> **Highest-regression seam.** `lang/base.py · chapter_identities:107` is the live cycle-breaker
> that produces all three id namespaces together; moving recognition without disturbing it
> is the delicate part. **Resolves BR-021** (position-based chapter identity) and
> **supersedes BR-019 / BR-020** (stable id, single ordinal model) — close those in
> `docs/decisions/branch_register.md` when S9.2 lands.

### S10 — Integration & migration, §7.2–7.4 (F2/F3/F4) `BUILD`

| ID | Deliverable | Refs | Deps | Done-when (tier) | Tag | St |
|---|---|---|---|---|---|---|
| S10.1 | **F4** read-only adapter: L2 blocks → legacy `{id,title,part,text}` (`text = "\n\n".join(paragraph projections)`) behind reconcile; B runs **structure-first** (D29). Read-only — never a write-back path; it is also the **rollback surface** (a regressing consumer reverts to the adapter) | §7.4; D16, D26, D29; O5 | S4.5 | existing consumers pass unchanged against the adapter | `BUILD` | `TODO` |
| S10.2 | Consumer migration, **triage first** (in-place rewriter `triage.py:286–327` → edits become governed L2/L3 patches), then `cleanup.py:915/935` (the `ch["text"]` reads; `:882` is the input-load), then `validate.py:432–465` — one BR at a time; **a regressing consumer reverts to the S10.1 adapter**; the adapter is retired only when **all** consumers are green off it | §7.4; D26 | S10.1, S8.2 | each migrated consumer drops the adapter, reads blocks; suite stays green | `BUILD` | `TODO` |
| S10.3 | **F2** replace `Structure` validator (`config/models.py · Structure:62`, the `h2_min`/`h3_count`/`parts` shape) with the general tree/blocks model + per-book structure map; `validate`'s count checks become assertions over the map, switching on S6 derived flags | §7.2, F2 | S4.5, S6 | validate asserts over the map; the S4.5 depth-0 fixture validates | `BUILD` | `TODO` |
| S10.4 | **F3** rework `ChapterIdentity` (`util/chapterids.py · ChapterIdentity:24`) → opaque `node_id` + rendered handles + aliases; `short`/`parse_md`/`html_slug` + provenance-key + revision-key become renderings of `(node_id, handle_policy)`; shifted handles recorded as aliases | §7.3, F3; D11, D33 | S4.3, S9.2 | **PLL golden** reproduces current boundaries + identities (no regression); alias table resolves retired handles | `GATE` (PLL golden) | `TODO` |

### S11 — Post-build evaluation: academic v1 ↔ v2 comparison (diagnostic, **not** a gate)

Runs **after** a full PLL-v2 extraction exists. Purely diagnostic — it measures how the new
extraction techniques performed; it has **no pass/fail threshold and must never become one**
(`feedback_no_cheating_results`). The engine writes its report under
`books/per_la_liberta/work/`; it reads v1 artifacts and the review-phase ground truth
**read-only** from the live tree (reading the live tree is allowed; writing it is not).

| ID | Deliverable | Refs | Deps | Done-when (tier) | Tag | St |
|---|---|---|---|---|---|---|
| S11.1 | v1↔v2 difference characterization: best-effort align the v2 extracted/reconstructed Italian against v1 `[live] output/italian_clean.md` (fuzzy / node-aligned — **not** 1:1, since segmentation differs by design) and report divergences by class (spaces/fragments reconstructed, word-form changes, structural shifts) + counts | user request (academic comparison); §3 (S3 changes text by design) | S3, S4.6, S10.1 | a written report enumerating divergence classes + counts | `SCAF` (diagnostic) | `TODO` |
| S11.2 | **Accuracy vs the deviation-review ground truth:** for each scan-confirmed deviation from the review phase (the hand-adjudicated set; `REVIEW.md` — exact artifact located at impl, «unverified» filename), did v2 extraction *independently* produce the adjudicated-correct form? Report **recall** (known-bad spots v2 fixes) + a **sampled** check for v2-introduced novel deviations | user request; `project_deviation_review_state`, `project_blind_read_signal` | S11.1 | a report giving recall vs the ground-truth set + the sampled false-change rate; **no threshold gate** | `SCAF` (diagnostic) | `TODO` |

> Why this is the right yardstick: the review phase already produced a **hand-adjudicated,
> scan-confirmed** set of where v1's OCR/cleanup went wrong. Measuring whether the new
> geometry + Zipf-DP + oracle extraction *independently* lands the same corrections is a far
> stronger academic signal than diffing two texts that were never 1:1. The **English-level**
> comparison waits on the v2 translation (M4c, paused) and is a later extension.

---

## Axis-level Definition of Done (PLL v2 ready)

The document-structure axis is shipped for PLL v2 when **all** hold:

1. **No regression** — the PLL golden reproduces current chapter boundaries + every
   identity through the new model (S10.4).
2. **Raw floor** — byte-exact raw round-trip passes for every captured atom (S1.2).
3. **D18 green** — the depth-0 / designation-string second-structure fixture passes; the
   schema generalizes beyond PLL's shape (S4.5).
4. **Re-bind proven** — geometry + fuzzy fingerprint re-attach binds correctly, **fails
   loud** on ambiguity, and the threshold is calibrated by measurement (S5).
5. **Alignment durable** — IT↔EN alignment is an L3 relation over `node_id`/`SpanRef`,
   not a reused index; the `typeset.py`-class mispoint is structurally impossible (S7.2).
6. **Governance live** — the structure map is the regen-guarded, stale-fail source of
   truth; the negative battery is green with no skip-masking (S5.2, S8).
7. **Scale honored** — structure ops stay sub-quadratic to the design ceiling (S4.7, D35).
8. **Neutrality holds** — core `structure/` carries no language/structure literal; all book
   opinion is in the profile + structure map (S0.2, S9).

S11 (academic v1↔v2 comparison) runs *after* this DoD is met and a v2 extraction exists — a
diagnostic that reports how the new techniques did, **not** a ship gate.

---

## Cross-track relationships

- **Engine-framework port milestones** (separate `engine-framework` line, `project_engine_framework_fork`):
  this axis is the deepened **M7 (extraction)** territory; **M4c (translate + refine)** is
  paused behind it. S10.2's triage migration sits on top of the **M4b** triage/cleanup that
  already landed — the adapter (S10.1) is what keeps M4b green during the cutover.
- **Branch register** (`docs/decisions/branch_register.md`): S9.2 **resolves BR-021** and
  **supersedes BR-019 / BR-020**; record the closure there when it lands.
- **Live PLL is evidence, not target for fixes** — `[live] typeset.py:609` (S7.2) and the
  `[live]` `corrections.json` anchor tombstone (S5.1) are cited as design evidence
  (`feedback_existing_path_failures_as_evidence`); their *operational* fixes belong to the
  deploy-hold track, not this branch.

## Deferred ledger (carried, not tasks)

| Item | State | Revisit condition |
|---|---|---|
| **O2** — recognition packaging (profile read by core vs thin `StructurePlugin` class) | deferred by choice | settles at S9.1 implementation |
| **O3** — HITL scale **ceiling** (the human container-authoring surface) | deferred by choice | only if a real corpus stresses the HITL **container** surface; the *algorithmic* scale of D35 is **now tested** (S4.7), distinct from this human-surface ceiling |
| **O4 / D32** — overlapping / interleaved hierarchy | parked | a target needs discontiguous interleaving (Hamlet) or geometrically-parallel marginalia; reserved `participates-in` hook only (S7.3b) |

---

## § Audit log

### S3 ↔ golden — RESOLVED (2026-06-26)

The first audit flagged S3 (space/fragment reconstruction) as orphaned in the DAG and the
graph parenthetical "(PLL golden also needs S3)" as inconsistent with `S10.4`'s deps.
**Resolution (user-confirmed):** "no regression" means **structural fidelity, not
byte-identical text** — v2 is *allowed and intended* to read better than v1 where S3 recovers
split/fragmented words the live pipeline never reconstructed. So the PLL golden (S10.4)
validates **structure** (boundaries + identities) and gains **no** S3 dependency; S3 is
pinned by its **own** space-recon tier (S3.2) + the raw round-trip floor (S1.2), feeding the
v2 **instance**, not the regression golden. The graph parenthetical is dropped (the rewrite
never carried it). **Added on top:** an academic, post-build v1↔v2 comparison (**S11**) that
measures the new extraction's accuracy against the review-phase scan-confirmed deviation set
— diagnostic only, never a gate. _Thread struck._

_(Further adversarial threads land here as `@@@@@@` blocks with paired `======` responses;
fold resolved outcomes into the affected task + spec section, then strike the thread.)_
