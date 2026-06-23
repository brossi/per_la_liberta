# Branch Register

> Forks *seen and not taken*, and one-way-door decisions: the alternative, why passed now, and
> the revisit condition. A recorded passed-branch is **deferred, not lost.** Append-only.
> See `engine/docs/port_discipline.md` §4–§5. Deferral is never to save effort — only when
> intervening work resolves an open question the decision needs.

---

## BR-001 — adjudicate: own step vs. special case of the M6 oracle
- **Opened:** 2026-06-22 (M3 planning).
- **Context:** adjudicate's Zingarelli-only lookup is a special case of the planned M6 ≥2-of-N
  period-dictionary membership oracle.
- **Taken now:** port adjudicate's code in M3 behind a thin interface; keep Zingarelli-only and
  faithful.
- **Not taken:** re-express adjudicate on the general oracle now.
- **Why defer (information, not effort):** the oracle does not exist until M6; deciding now would
  commit blind. M6 builds it and is the point of maximum information.
- **Revisit:** M6, when the oracle exists. (See `ENGINE_M3_PLAN.md` D3.)

## BR-002 — non-Italian separability fixture: build now vs. after the language steps
- **Opened:** 2026-06-22 (governance review).
- **Context:** the synthetic book is Italian, so it tests structural injection, not language
  generalization; the language-axis seams (`word_score_accents`, consonant alphabet, period
  dictionaries) are untested for any non-Italian text.
- **Taken now:** defer; the limit is named in `port_discipline.md` §6.
- **Not taken:** build a non-Italian fixture now.
- **Why defer (information, not effort):** built now it would not know which seams to differ on
  and would pass trivially (the single-fixture blind spot). Porting the language-config-consuming
  steps resolves *what it must exercise*, so a later fixture is built to differ where it matters.
- **Revisit:** after the language-config-heavy steps are ported (M4b cleanup is the largest
  consumer); at the latest before M7 extraction, which claims portability.

## BR-003 — re-baseline-cites-ledger enforcement: automate now vs. review-enforce
- **Opened:** 2026-06-22 (governance review).
- **Context:** the anti-cheat rule (a `*_expected` golden change must cite a divergence or refresh
  entry) needs enforcement.
- **Taken now:** the rule is binding and **review-enforced** (human); stated in `port_discipline.md`
  §5.
- **Not taken:** build an automated check now.
- **Why defer (information, not effort):** no re-baseline workflow exists yet to enforce against;
  building the check now is speculative. M3 produces the first golden and the first possible
  re-baseline.
- **Revisit:** if/when re-baselines become frequent enough that human enforcement is unreliable
  (no earlier than M3's first re-baseline).

## BR-004 — running-head marker: book title lifted out of the *language* plugin (RESOLVED)
- **Opened:** 2026-06-22 (M3 reconcile port / separability work).
- **Context:** `ItalianLanguagePlugin.split_raw_chapters` dropped a running-head line via a
  hardcoded `_PER_LA_LIBERTA_RE = r"\s*PER\s+LA\s+LIBERT[AÀ]!?\s*$"` — that marker is the **book
  title**, not an Italian-language fact, yet it lived beside genuinely language-level markers
  (PREFAZIONE / PARTE SECONDA / FINE DELLA PRIMA PARTE, which are Italian structural *words*). The
  synthetic separability fixture exposed the seam: a non-PLL book has a different running head (or
  none), so the title marker was correct only by accident.
- **Resolved 2026-06-22 (user decision — lift now, do not defer):** for the language plugin/config
  to be a true cross-title resource, the title must not live there. Lifted to **book-level**
  config: new `manifest.structure.running_heads` (a list of regex bodies); the plugin now takes
  `running_heads` as a parameter and anchors each as `\s*(?:<body>)\s*$`, and `reconcile.run`
  passes `cfg.structure.running_heads`. PLL declares `["PER\\s+LA\\s+LIBERT[AÀ]!?"]`; synthetic
  declares `[]`. The Italian structural *words* (PREFAZIONE/PARTE/FINE) stay in the plugin — they
  are language-level and cross-title.
- **Equivalence preserved:** the anchored config pattern reproduces the live marker exactly —
  `test_reconcile_golden` still reproduces (byte-identical).
- **One-way-door note:** this added a `manifest.structure.running_heads` field (config schema
  change). Proven config-driven, not plugin-baked, by
  `test_running_head_drop_is_book_config_not_plugin_baked`.
- **Required, not optional-with-default (rationale):** the field is schema-**required** with no
  code default. Every book declares it explicitly — `[]` is the explicit "this book has no
  running heads", distinct from a forgotten field — so segmentation behavior is always visible in
  the manifest and never silently implicit. This matches the sibling `structure` fields, which are
  all required, and the engine's no-baked-default principle. The cost is one line of boilerplate
  (`"running_heads": []`) for a book that has none; accepted in favor of explicitness. (If a future
  book load proves this boilerplate burdensome, making it optional-defaulting-to-`[]` is a
  backward-compatible schema relaxation.)
- **Why decide now (not defer):** the user called it; a cross-title language layer is a standing
  requirement, not something a second book is needed to clarify. (Other non-cross-title data still
  in the language layer — the Bodoni-scan ordinal garbles — is a separate *homing* concern,
  audited and deferred as **BR-006**; distinct from **BR-002**, which is about a non-Italian test
  fixture, not where scan-noise lives.)

## BR-005 — adjudicate result contract: bare dict vs. self-describing envelope (one-way door)
- **Opened:** 2026-06-22 (M3 adjudicate port; decided with the user).
- **Context:** live `adjudicate.main()` wrote a bare `{chapter_id: [...]}` and, with no input, an
  empty `{}` — which is ambiguous (zero results vs. no input vs. an upstream failure that ate the
  flags). adjudicate has no equivalence golden (F2/D3) and no current consumer (triage, M4b), so
  the output shape is still open to design.
- **Taken now (decided, not deferred):** `run` always writes a self-describing envelope
  `{"input_present", "tokens", "stats", "results"}`. A missing input is an **explicit** no-input
  envelope (`input_present: false`, empty `results`), distinguishable from a populated run and from
  a silent `{}`. Classified entries inside `results` stay byte-faithful to live.
- **Not taken:** stay faithful to the bare-dict / empty-`{}` shape.
- **Why decide now (not defer):** the user called it explicitly; the ambiguity is a real
  upstream-failure-masking hazard worth removing before any consumer is built against the shape.
- **One-way-door note:** this is the step's output contract. M4b's `triage`/consumers read
  `envelope["results"]`. Not a divergence-ledger entry (orchestration contract, not an
  algorithm change licensed by ground truth — the ledger forbids unlicensed entries; §2/§5).
- **Revisit:** only if a consumer needs a different shape (M4b).

## BR-006 — Bodoni-scan OCR garbles living in the cross-title language plugin
- **Opened:** 2026-06-22 (M3; book-vs-language audit the user requested after BR-004).
- **Context:** beyond the title (BR-004), `ItalianLanguagePlugin` still holds data that is *not*
  Italian-language fact but **PLL's specific Bodoni-scan OCR damage**:
  `ORDINAL_FIXES` (`"dccimoscttimo"→"decimosettimo"`, `"qyinto"→"quinto"`, …), `WORD_FIXES`, the
  garble entries baked into `_ITALIAN_NUMBERS` (`"O^indiccsimo": "Eleven"`, …), and the
  `[GC][a-z]*pitolo` OCR tolerance in `_HEADING_RE`. These are the *scan-noise* analog of the
  title: inert (not wrong) for another Italian book, but they'd accumulate per-book garbles in the
  shared Italian layer. Their natural relative is the `source_noise`/`bodoni_didone` profile (which
  already holds Bodoni fixes like `cbe→che`). This placement was a **deliberate** plan decision
  ("observed-scan data the plugin owns… routes all four ordinal tables here"), not an oversight.
  *(Adjacent, separate axis: `bodoni_didone.json`'s `substitution_rules` are themselves
  Italian-word-specific — that profile is "Bodoni ∩ Italian," not pure typeface. Noted, not this
  entry's subject.)*
- **Taken now:** leave them in the plugin, faithful to the plan's routing; inert for PLL and any
  non-matching book.
- **Not taken:** design the `source_noise`↔plugin seam and move the garble tables out now.
- **Why defer (information, not effort):** unlike the title (a one-line check with an obvious
  manifest home, *actively wrong* for other books), these are **entangled with `parse_chapter_number`'s
  logic** and some map garble→English directly. The clean seam — does `source_noise` grow an
  ordinal-garble map? does the plugin take a garble dict keyed by the source-noise profile? — is
  genuinely unclear, and designing it against *only* PLL's garbles is the single-fixture blind spot.
  A second Italian (esp. same-typeface) book supplies the concrete second garble set to design the
  seam against.
- **Revisit:** when a second Italian/same-typeface book is added, or at M7 extraction (which claims
  portability). Pairs with BR-004 (book-identity lift, done) and BR-002 (non-Italian fixture).

## BR-007 — source_noise: literal word-fixes vs. a layered character-confusion model
- **Opened:** 2026-06-22 (M3; `source_noise` audit extending BR-006, user discussion).
- **Context:** `bodoni_didone.json`'s `substitution_rules` are literal `garble → word` pairs
  (`eolla→colla`, `cbe→che`, `5AN→SAN`, `piii→più`) that **bake together two independent facts**:
  a typeface *character confusion* (`c↔e`, `h↔b`, `S↔5`, `u/n→ii`) and a specific *Italian target
  word*. So the profile is really "Bodoni ∩ Italian ∩ observed-scan", not pure typeface.
  `boundary_substitutions` (`{i:[r,e]}`) is the clean char-confusion form — applied generatively
  and dictionary-validated by cleanup.
- **Two paths weighed:** (1) keep literal substitution rules per profile (status quo); (2) factor
  substitutions and elevate ones that recur across typefaces into a shared/general layer.
- **Taken now:** Path 1. Treat `substitution_rules` as observed literal word-fixes — the same
  family as BR-006's ordinal garbles (specific, per profile).
- **Not taken:** Path 2 — a layered {general OCR-universal + per-typeface} character-confusion
  model.
- **Why defer (information, not effort):**
  - The entangled thing (the *literal pairs*) is a **product** of typeface × word × scan; a
    different face garbles differently, so literal pairs rarely recur across typefaces — elevating
    them yields a near-empty "general" section = overhead (the user's own suspicion).
  - The genuinely elevatable unit is the **character confusion**, not the word-pair (the cases
    that do recur, e.g. `5↔S`, recur *because* they are char confusions). That is a different,
    currently tiny surface (`boundary_substitutions` is one rule today).
  - You cannot tell which confusions are "universal" vs. Bodoni-specific from a single typeface —
    the same single-fixture blind spot as BR-006.
  - The generative machinery that makes a confusion model pay off (apply confusions → validate
    against the period dictionary) lives in **cleanup (M4b)**; elevating the model before its
    consumer exists is schema-without-a-consumer.
- **Sharper seam recorded:** "per-typeface" is itself imprecise — `substitution_rules` are
  *language-bound* (a German book in Bodoni couldn't reuse them as-is). The real seam is
  **char-confusion (language-neutral, layerable)** vs. **literal word-fix (language-bound,
  specific)**, *not* per-typeface vs. cross-typeface. Cut that seam when a 2nd typeface and/or 2nd
  language exists to design against.
- **Revisit:** when a 2nd typeface and/or language is added, and/or during M4b cleanup (where the
  confusion→dictionary mechanism lives). Pairs with BR-002 (non-Italian fixture) and BR-006
  (scan-noise homing).

## BR-008 — prompt-context contract: the book-identity vs. language-fact boundary (one-way door)
- **Opened:** 2026-06-22 (M4 planning; decided with the user, `ENGINE_M4_PLAN.md` D2).
- **Context:** M1 left `manifest.prompt_context` a free dict ("keys defined by the M4 prompt
  templates"). M4a's OCR template is the **first consumer** → it fixes the first keys and the
  render-context contract every later prompt (triage / cleanup / translate / refine /
  multi-eval / synthesis / provenance) inherits. The live `OCR_PROMPT` (`ocr.py:27-38`)
  **hardcodes — as literal text, not interpolated —** a *mix* of book facts (title, author, year) and
  language facts (the language name "Italian"; the accent inventory `à è ì ò ù é`) in one flat blob; the seeded PLL
  `prompt_context` likewise carries `language_name` beside book identity — a latent redundancy
  (`language_name` is already implied by `language_id`) and a blurred layer boundary.
- **Taken now:** a clean **two-layer, namespaced** boundary (three layers counting the
  book/language-neutral engine template itself):
  - `manifest.prompt_context` = **book-identity facts only** (`book_title`, `author`, `year`,
    `subject`, `entities`) → `{{ book.* }}`;
  - the **language profile** = cross-title **language facts** (a human-readable display name; the
    accent inventory) → `{{ language.* }}`;
  - render context = the namespaced merge; the template *files* are book-neutral and
    profile-resident (`engine/profiles/prompts/`), rendered by the engine-owned Jinja2 machinery
    (`src/engine/prompts/templating.py`) with **`StrictUndefined`** (a missing key is a hard error,
    not silent empty).
  Mirrors **BR-004** (which lifted the book *title* out of the language plugin): book facts in the
  book layer, language facts in the language layer.
- **Not taken:** keep `prompt_context` as the live flat blob (`language_name` beside book identity)
  — faithful, but redundant, boundary-blurred, and it would let a language fact vary per book.
- **Schema implications (executed at M4a porting; the field-level choices are two-way doors):**
  drop `language_name` from `prompt_context`; add a language **display name** to the
  `LanguageProfile` schema (the profile has `language_id` but no human-readable name today); the
  prompt accent inventory is **single-sourced from the profile** (likely the lowercase run of
  `word_score_accents`, or a dedicated prompt-facing field — decided at porting). The *boundary* is
  the one-way door; the field names are not.
- **Why decide now (not defer):** the OCR template is the first consumer and freezes the
  render-context contract every later prompt reads (the M4b/M4c prompts triage/cleanup/translate/refine
  plus M5's multi-eval/synthesis/provenance); deciding the boundary before they bind to a blurred one
  is the point of maximum leverage. The user called it.
- **Revisit:** only if a later prompt needs a fact that fits neither layer (e.g. a scan /
  source-noise fact) — extend the namespaced context with a *third* source rather than collapsing
  the boundary.

## BR-009 — M4a acquisition backend seams: purpose-built minimal seams vs. unified `providers.py`
- **Opened:** 2026-06-22 (M4 planning; decided with the user, `ENGINE_M4_PLAN.md` D1). *(Numbering
  follows that plan's reservation: BR-008 prompt-context contract is above; BR-010 OCR model-id
  home and BR-011 triage taxonomy to follow at porting.)*
- **Context:** M4a's `download` and `ocr` cross three external boundaries that must be injectable for
  offline property/separability tests — HTTP fetch (`download`), PDF page render (`ocr`, PyMuPDF),
  and the vision-OCR model call (`ocr`, Gemini). M5 separately plans a unified `providers.py`
  *TranslationProvider* abstraction. Fork: build the unified provider now and route OCR through it,
  or stand up minimal purpose-built seams.
- **Taken now:** three minimal injectable seams in M4a — `Fetcher.fetch(url)→str`,
  `PageRenderer.render(pdf,page,*,dpi)→bytes`, `OcrBackend.transcribe(image,prompt)→str` — each
  defaulting to the real backend (requests / fitz / Gemini) and injected via
  `run(*, ws, cfg, lang, fetcher=None, renderer=None, backend=None, **opts)`. `providers.py` is left
  a stub. Mirrors M3's injected `DictionaryOracle` (BR-001).
- **Not taken:** pull `providers.py` (M5) forward and express OCR through it.
- **Why decide now (not defer):** the user called it, and the alternative is *actively worse*, not
  merely premature — `providers.py` is the **translation** (text→text) provider family, while these
  are **acquisition** operations (image→text vision; pure IO with no model). Designing the unifying
  translation abstraction against OCR-only is the single-fixture blind spot. The seams are **siblings
  of `providers.py`, not a premature version of it** — they never converge, so "minimal now" is not
  throwaway work.
- **Two-way door:** a seam signature behind a step function is cheap to change (§4) — no config
  schema, no locked-in consumer. If multi-model OCR later wants a different shape, change it then.
- **Scope split (M4a vs. M4c):** the *acquisition* seams are M4a (this entry, resolved). The distinct
  question — whether M4b/M4c's **chat** calls (triage / cleanup-LLM / translate / refine, all
  text→text) should share the seam `providers.py` generalizes — is the real `providers.py`-prefiguring
  decision and is **deferred to M4c's formal development**, not settled here.
- **Revisit:** M4c (chat-seam ↔ `providers.py` relationship); M5 (the unified provider family
  itself). The acquisition seams themselves revisit only if a backend's modality changes.

## BR-010 — OCR model ids: per-book manifest block vs. baked code default (one-way door)
- **Opened:** 2026-06-22 (M4 planning; decided with the user, `ENGINE_M4_PLAN.md` D3).
- **Context:** live `ocr.py:22-25` bakes frontier ids (`gemini-2.5-flash`,
  `gemini-3.1-pro-preview`) as a code constant. The framework risk note forbids shipping frontier
  ids as stable engine defaults, and model ids rot on a regular cadence as new models ship (user).
- **Taken now:** a per-book **`manifest` `ocr` block** carrying the model ids (flash/pro roles → ids)
  and related acquisition details, explicit, with **no engine default** — and giving provenance
  (which model produced `copy3`).
- **Not taken:** (b) a CLI-only flag with no default (loses the recorded provenance); (c) keep the
  ids as a code constant (bakes a frontier id — violates the risk note and the no-baked-default
  principle).
- **One-way door:** config-schema shape (manifest gains an `ocr` block → schema + loader + models).
- **Why decide now (not defer):** the user called it; model-id rot is a standing concern, not
  something a second book clarifies.
- **Revisit:** the block's field-level shape (does `dpi` / JPEG quality / a prompt-template ref live
  here?) is finalized at **M4a porting** (two-way door); the *existence* of a per-book model-id block
  is settled.

## BR-011 — triage disagreement taxonomy: general code-default, not a deferred-language item
- **Opened:** 2026-06-22 (M4 planning; decided with the user, `ENGINE_M4_PLAN.md` D5). Executed at
  M4b porting.
- **Context:** live `triage.py` classifies OCR-witness disagreements via a `classify_disagreement`
  tool whose `category` enum is `{ocr_confusion, ocr_corruption, punctuation_artifact,
  alignment_drift, missing_text, archaic_spelling, unknown}`, inside a `TRIAGE_SYSTEM` prompt that
  *also* carries Italian/Bodoni example patterns and physical-witness descriptions.
- **Taken now — decompose by actual nature, not by surface appearance:**
  - **category enum + tool schema → code default**, because the labels are a *general*
    OCR-disagreement taxonomy (none is Italian; `archaic_spelling` is era-general). Settled general
    engine logic.
  - **OCR example patterns → config** via the prompt template (`source_noise` char-confusions +
    language accento), the BR-008 machinery.
  - **witness descriptions → `manifest.sources[].label`** (already present) + the ocr-produced
    `copy3` role.
- **Not taken:** lift the enum to `LanguageProfile`/manifest now — rejected: it is **not language
  data**; configuring it would be speculative generality (engine-agnostic / let-the-fixture-pull-it).
- **Correction recorded (own framing):** the original plan called this the *"Italian-OCR category
  enum"* and treated the code default as a 2nd-language deferral (single-fixture blind spot). On
  reading the seven members they are language-neutral → reframed to **"code-default because
  general."** The labels are general; whether these exact seven are the *universal* set or merely
  PLL's is the lone residual generalization question.
- **Revisit:** only if a real second book needs **different categories** (a genuine "second book
  forced it") — **not** an expected language deferral, and distinct from BR-002 (a non-Italian *test
  fixture*, not this taxonomy).

## BR-012 — engine regen-guard for destructive steps: owed at M4b/M4c, not M4a
- **Opened:** 2026-06-22 (M4 planning; `ENGINE_M4_PLAN.md` D6 follow-up, user-raised).
- **Context:** the live pipeline guards `cleanup`/`translate`/`all` behind an interactive
  `regenerate <step>` TTY prompt + a `.claude` deny-list + a `PER_LA_LIBERTA_ALLOW_REGEN` escape,
  because they overwrite committed, hand-tuned, non-reproducible text. D6 settled that M4a's
  `download`/`ocr` need **no** such guard: their outputs (`copy*`) are reproducible acquisition, not
  hand-tuned, and the `BookWorkspace` sandbox already makes a stray run harmless to the live tree and
  the frozen `inputs/`.
- **The catch (user):** the sandbox protects the live tree and `inputs/`, but **not hand-tuned /
  expensive artifacts *within* `work/`**. `cleanup` (`work/output/italian_clean.md` — hand-edited in
  the deviation-review workflow) and `translate`/`refine` (`work/state/translations/` — the
  irreproducible synthesis + refinements) **are** destructive to re-run even inside the sandbox — the
  same hazard the live guard addresses.
- **Taken now:** **no guard in M4a** (acquisition is non-destructive). The destructive-step guard is
  **owed at M4b (cleanup) and M4c (translate/refine)**, designed there against the concrete
  protectable surface.
- **Not taken:** design the guard seam now (M4a). Rejected as speculative — M4a has nothing to
  protect, and M4b/M4c's exact hand-tuned/expensive surface isn't known yet. The guard is an
  **additive top-of-run check** (a step refuses to overwrite existing protectable output in `work/`
  without an explicit override) — a **two-way door** that forecloses nothing and is cheap to add when
  its consumer is concrete.
- **Mechanism note (for M4b/M4c, not decided now):** the engine's guard is **workspace-internal**
  (detect protectable output in `work/` → refuse without an explicit override). This **revises** the
  framework plan's earlier guard sketch (lines 216-220: a per-book `ENGINE_ALLOW_REGEN` env escape +
  `.claude` deny entries) — the detection-based refusal is the settled core, **not** a copy of the
  live TTY / deny-list / `PER_LA_LIBERTA_ALLOW_REGEN` construct (a live-tree + Claude-settings
  mechanism). The two reconcile: the "explicit override" can *be* `ENGINE_ALLOW_REGEN`, so the open
  M4b decision is the **override's form** (env flag? deny entries? both?), not whether detection-based
  refusal is the mechanism.
- **Revisit:** M4b (cleanup) and M4c (translate/refine) — each decides its guard before its first run
  that can overwrite expensive/hand-tuned output. Pairs with the live regen-guard rationale (CLAUDE.md).

## BR-013 — `inputs/` fixture lifecycle: the frozen-fixture vs. engine-producible shadow
- **Opened:** 2026-06-22 (M4 planning; `ENGINE_M4_PLAN.md` D7 follow-up, user-raised).
- **Context:** D7(b) adds `books/<id>/scans/` for the raw PDF, distinct from `books/<id>/inputs/`
  (frozen golden fixtures). That sharpened a parallel/shadow concern: as step *producers* get ported
  (M4a `download`/`ocr`; M3 `reconcile`; M4b `cleanup`), the engine can itself produce artifacts that
  `inputs/` also holds frozen — risking duplication/divergence and source-of-truth ambiguity. **Not
  hypothetical:** as of M3, `validate`'s golden already reads a *frozen* `inputs/reconciled_chapters.json`
  that engine-`reconcile` can now produce.
- **Key distinction — not all of `inputs/` is shadow-risky:**
  - **non-deterministic-step outputs** (`copy{1,2,3}` + page maps) — the *irreducible* deterministic
    test-entry point; a test can never regenerate them (network/LLM). **Permanent; never removed.**
  - **deterministic-step outputs** (`reconciled_chapters`, `clean`-detcore, `chapter_pages`) — the
    engine can reproduce them → the **shadow-risky subset**.
  - **F1 wrinkle:** some frozen deterministic outputs are *hand-edited* (`validate`'s frozen
    `reconciled_chapters.json` is 2 lines off pristine engine output, M3 F1) — intentionally distinct,
    so chaining would *lose* the edits and a naive drift-check would flag them.
- **Taken now (principle):** `inputs/` is the permanent deterministic-test-input layer and is **not**
  removed wholesale. The shadow-risky subset is resolved **per deterministic producer as it is
  ported**, default **keep + drift-guard** (a consistency test pinning frozen == engine-produced for
  unedited cases; hand-edited F1 fixtures carry a logged "diverges by intent" note instead),
  **retire-via-chaining** only where a fixture is purely mechanical and isolation isn't worth the
  upkeep.
- **Hard forcing function — M7 (extraction).** The subtree-split clone must build + pass tests
  **self-contained**, and the framework plan's current mitigation ("refresh `inputs/` from live")
  **dies at extraction** (no parent/live tree to refresh from). So by M7 the fixture graph must be
  coherent, minimal, and non-shadowed; **the shadow cannot survive M7.**
- **Not taken:** remove/disable `inputs/` now (breaks every golden — the non-det entry points are
  irreducible); or defer the whole question blind to M7 (risks discovering a shadow mess at the worst
  time).
- **Revisit:** per deterministic producer as ported — the first concrete case is `validate`'s frozen
  `reconciled` (evaluable now; F1 hand-edits make it non-trivial), then M4b `cleanup`'s outputs;
  **final coherence enforced at M7.** Pairs with the framework plan's "Duplication/divergence" risk
  and `port_discipline.md` §5 "Input refresh."
