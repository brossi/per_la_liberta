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
