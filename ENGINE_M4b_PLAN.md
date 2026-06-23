# Engine M4b Plan — Text mutation (`triage` + `cleanup`)

> Standalone review artifact, the focused sub-plan `ENGINE_M4_PLAN.md` promised cleanup when
> reached ("the codebase's largest single file… it gets one then"). Audit inline with `@@@@@@`
> blocks; I'll answer each with a paired `======` (code-verified, per point) before porting.
> Anchors here are read **directly against the live tree** (`triage.py`, `cleanup.py`) and the
> ported engine (M4a idioms) at plan time — not reconnaissance-level like the M4-plan sketch.

## Scope

- **`triage`** (`triage.py`, 350 ln) — LLM classification + resolution of the OCR disagreements
  `reconcile` couldn't settle; merges accepted corrections back into `reconciled_chapters.json`.
- **`cleanup`** (`cleanup.py`, 1509 ln, the largest single file) — deterministic OCR-artifact
  removal/correction (`use_llm=False`) **plus** an optional LLM correction pass (sync + Batch API).

**Order: `triage` first, then `cleanup`.** triage is the smaller, cleaner port (language-neutral
*code*; only its prompt carries Italian) and exercises the M4b chat seam + prompt-template reuse
that cleanup's LLM path then inherits. cleanup is the milestone's weight: the one M4 equivalence
golden (D4), the language-neutrality refactor, the regen-guard, and the new config field.

**Out of scope (explicit):**
- The **multi-witness** flag-review helpers in `cleanup.py` (`_call_gemini_flags`,
  `llm_fix_flagged_tokens`'s `verify=True` Claude+Gemini agreement path, `_FLAG_REVIEW_SYSTEM`)
  are a *second LLM provider* + cross-model agreement — that is the M5 multi-witness family, not
  M4b. M4b ports the **single-model** correction path (`llm_correct_italian` + Batch API); the
  flag-review duo is left for M5 (recorded under §Decisions M4b-D5). *(Verified orphaned:
  `llm_fix_flagged_tokens` has no caller in `cleanup()` or `pipeline.py`, so excluding it is
  behavior-neutral; the live cleanup's wired LLM path is `llm_correct_italian`.)*
- `typeset` (M3b, deferred), `translate`/`refine` (M4c).

---

## 1. Branch-register read-obligation dispositions (the first task, per `port_discipline.md` §5)

M4b is the milestone three deferrals named as their revisit point. Resolved here **with cleanup's
concrete surface in hand** (the honest plan promised in `ENGINE_M4_PLAN.md` §read-obligation), not
speculatively. Each is a recommendation to rule on; the disposition lands in `branch_register.md`
when porting.

### BR-002 — non-Italian separability fixture · **comes due · recommend: split the obligation**

The revisit condition ("after the language-config-heavy steps are ported — cleanup is the largest
consumer") is now satisfied: I can see exactly what a non-Italian fixture would have to differ on.
Reading cleanup, its language coupling is **two distinct kinds**, and they want different answers:

1. **Config-resident language coupling** (frequency dictionary, spaCy model, the `source_noise`
   tables) — already external to code, swapped by pointing the manifest/profile elsewhere. The
   *existing* synthetic book (Italian plugin, but its own manifest/profiles) already proves these
   are config-driven for the structural axis.
2. **Italian opinion baked into cleanup's *step code*** — accent-fold table (`_ACCENT_MAP`),
   accented-vowel character classes (`àèìòùé`, `À-ÿ`) scattered through ~a dozen regexes, the
   accented-lowercase continuation rule in `join_broken_paragraphs`. **This is the real BR-002
   bite**, and it is a code-neutrality defect (I4: a *step* must carry no language opinion; only
   `lang/italian.py` may), not something a test fixture reveals — it is visible by reading.

**Recommendation — decompose, don't build-or-redefer wholesale:**
- **Resolve the code-neutrality half *now*, as part of the port** (mandatory) — and fully into the
  **config layer**, not a plugin method (D1, locked): the accent-fold map → a language-profile
  `accent_fold` field (generic `str.translate` helper in `util.text`); the restrictive
  accented-letter char-classes → one **presumed canonical superset** field used at every site,
  validated by the detcore golden (a site where the superset changes live output turns the golden
  red → faithful-revert or a `DL`-licensed divergence, never silent); the redundant `:486`
  continuation clause → neutral `.islower()`; the `[À-ÿ]` *ranges* → a `word_letter_class` profile
  field (a *script* fact, not code — verified distinct from `coverage.letters` on the glyph `ó`).
  Prove it with I4's core-neutrality scan **plus** a new unit test asserting **no Italian
  character literal remains in `steps/cleanup.py`** (sets sourced from `cfg`/`lang`). adjudicate's
  identical in-step `_ACCENT_MAP` reconciles to the same `accent_fold` source.
- **Re-defer the *full non-Italian fixture* to M7** (the extraction forcing function): a fixture
  that genuinely bites needs a *second registered `LanguagePlugin`* + a non-Italian frequency
  dictionary + a non-Italian spaCy model — heavy, and its residual value over the
  neutrality-refactor-plus-scan is catching a *semantic* Italian assumption with **no** tell-tale
  literal, which BR-002 itself says a single speculative fixture can't pre-design. M7 builds it
  against the real second book/language and is the hard deadline that *claims* portability.

This is **not** redeferral-to-save-effort (forbidden): the intervening work (porting cleanup)
resolved the open question — *what must a fixture differ on* — and the answer split into a part we
do now (code neutrality) and a part whose information is still missing until a real second language
(the semantic axis). We name the question and the revisit condition, as required.

### BR-006 — Bodoni ordinal garbles in the Italian plugin · **re-read · recommend: re-defer**

`ENGINE_M4_PLAN.md` expected cleanup to *consume* these. Reading both: **cleanup does not touch
them.** The ordinal garbles (`ORDINAL_FIXES`, `WORD_FIXES`, the `_ITALIAN_NUMBERS` garble entries,
`_HEADING_RE`) are consumed only by `parse_chapter_number` (reconcile's heading detection, **ported
in M3**) and `title_to_english` (translate, **M4c**). cleanup consumes a *different* table —
`source_noise.substitution_rules` (the `eolla→colla` word-fixes), which is BR-007's subject, not
BR-006's. So M4b's re-read confirms cleanup is not BR-006's consumer; the disposition is unchanged:
**re-defer** to "a 2nd Italian/same-typeface book, or M7" (no second book exists). M4c will re-read
it again as translate's title path *is* a real consumer.

### BR-007 — literal word-fix vs. layered char-confusion model · **comes due · recommend: re-defer the layering; record that placement is already resolved**

cleanup is the consumer BR-007 named ("the confusion→dictionary mechanism lives in cleanup"). Now
visible: cleanup applies **both** kinds, and they are **already config-resident** in
`bodoni_didone.json` —
- `boundary_substitutions` (`{i:[r,e]}`, the clean language-neutral *char-confusion* form) drives
  the generative dehyphenation passes (`dehyphenate_token` 2/3), already proven config-driven by
  adjudicate's M3 port which reuses the same field;
- `substitution_rules` (literal `eolla→colla` *word-fixes*) drive `apply_pre_filters`.

So the **placement** worry (are these baked in code?) is effectively **already resolved** — both
live in the `source_noise` profile, and cleanup will read them from `cfg.source_noise`. What stays
open is only the **layering** question (factor a general OCR-universal char-confusion layer from the
per-typeface literals). Disposition: **re-defer the layering** — it needs a 2nd typeface/language
to tell "universal" from "Bodoni-specific" (the single-fixture blind spot, unchanged), and
elevating a near-empty "general" layer now is overhead with no consumer. **Record the sharpening:**
M4b confirms placement is done; only the cross-typeface generalization waits. Revisit: 2nd
typeface/language, or M7.

---

## 2. BR-012 — workspace-internal regen-guard (designed here, against cleanup's concrete surface)

cleanup writes `work/output/italian_clean.md`. In the live tree that file carries hand-applied
deviation-review fixes (irreproducible) and is guarded behind the `regenerate cleanup` TTY prompt.
The engine has no live tree to endanger (the sandbox guarantees that, I7), but BR-012's catch
stands: the sandbox does **not** protect a hand-tuned artifact *within* `work/`. Once a human edits
`work/output/italian_clean.md`, a re-run of `cleanup` clobbers it.

**Mechanism (settled by BR-012):** detection-based refusal — an additive top-of-run check; if the
protectable output already exists, refuse to overwrite without an explicit override. **Open
question (BR-012 left it): the override's *form*.** Options (§Decisions M4b-D2):
- **(a)** a `run(..., allow_regen: bool = False)` kwarg, threaded from a new CLI `--allow-regen`
  flag **and** an `ENGINE_ALLOW_REGEN=1` env escape (the env mirrors the live
  `PER_LA_LIBERTA_ALLOW_REGEN`); refusal raises a typed `RegenerationGuardError` (new
  `EngineError`, next exit code 6).
- **(b)** kwarg + env only, no CLI flag (CLI added when an interactive human needs it).
- **(c)** CLI flag only.

**LOCKED (b) (2026-06-23):** `allow_regen` kwarg (the mechanism + what the guard's own test toggles)
+ global env `ENGINE_ALLOW_REGEN=1` (BR-012's anticipated form, mirrors the live
`PER_LA_LIBERTA_ALLOW_REGEN`; deliberate friction). **No CLI flag** — its only value over the env is
typing convenience (future-need-only, Principle 2), and discoverability is handled by the
`RegenerationGuardError` message naming the escape. Refusal stays inside the F7 taxonomy (clean exit
6, not a traceback). The CLI flag is a trivial two-way-door addition via the existing F7 threading if
a human later wants it. The detcore **golden generator** is unaffected: it runs in a temp dir, never `work/` (so the guard never fires there);
the guard guards the *step's* real run. The same guard is reused by `cleanup`'s LLM path and, at
M4c, by `translate`/`refine` (`work/state/translations/`).

**A subtlety to rule on:** in the engine `work/`, a *first* cleanup run has nothing to protect (no
prior `italian_clean.md`); the guard only bites on **re-runs**. That is correct and matches the
live guard (which exists precisely to stop a second, clobbering run). No provenance tracking
("is this file hand-edited or engine-made?") is attempted — the guard is conservative: *any*
existing protectable output blocks a silent overwrite. (Accepted: a user re-running deterministic
cleanup with no hand-edits must pass `--allow-regen` once. Cheap, and fail-safe.)

---

## 3. Findings from pre-port verification

**F1 — triage's *code* is already language-neutral; only its prompt is Italian.** Every function
(`_is_plausible_correction`, the resolution passes, `_apply_resolutions`) is pure string/structural
logic. The Italian/Bodoni content lives entirely in `TRIAGE_SYSTEM` (witness descriptions +
example OCR patterns) and the `CATEGORIES` enum. Per BR-011 the enum is a **code default** (general
OCR taxonomy); the prompt becomes a template (book facts + witness labels from config). So triage's
separability is nearly free — its code holds no opinion to extract.

**F2 — cleanup's deterministic core *does* hold Italian opinion in step code** (the BR-002 bite,
§1). Concrete inventory (file:line, live `cleanup.py`):
| Live literal | Kind | → destination |
|---|---|---|
| `NOISE_LINE_PATTERN` (`:14`) | source-noise regex | **new** `source_noise.noise_line_pattern` (the field models.py reserved for M4b) |
| `SUBSTITUTION_RULES` (`:20`) | source-noise word-fixes | `cfg.source_noise.substitution_rules` ✓ (exists) |
| `BOUNDARY_SUBSTITUTIONS` (`:76`) | char-confusion | `cfg.source_noise.boundary_substitutions` ✓ (exists) |
| `it_combined.txt` loads (`:56,90`) | frequency dict | `cfg.language.frequency_dictionary` + `require_asset` |
| `it_core_news_lg` (`:67`) | spaCy model | `cfg.language.spacy_model` |
| `_ACCENT_MAP`/`_strip_accents` (`:269`) | Italian accent fold | language layer (M4b-D1) |
| `àèìòùé`/`À-ÿ` classes in `is_noise_line`, `join_broken_paragraphs`, `_PUNCT_RULES`, `clean_text` | accented-vowel classes | language layer (M4b-D1) |
| inline page-marker regexes (`:601-603`) | source-noise | `source_noise` (join the existing artifact pattern) |
| `_FLIG_SUBS` f-ligature pairs (`:640`) | typeface ligature confusion | `source_noise` (new optional table) or keep — M4b-D3 |
| LLM prompts (`_LLM_CORRECT_SYSTEM` `:703`) | book+language facts | prompt template |

**F3 — the deterministic core *is* golden-able; its inputs must be pinned.** `cleanup(use_llm=False)`
reads `reconciled_chapters.json` (required), `chapter_pages.json` (optional, for page markers), and
`corrections.json` (optional, manual-overrides fallback). For a clean detcore golden (D4) the
generator runs the **live** `cleanup(use_llm=False)` over **frozen `reconciled_chapters.json` +
`chapter_pages.json`** with **no `corrections.json`** (so the golden is the pure deterministic
core, no manual overrides) in a temp dir. Version-sensitive on spaCy + symspell → pin both; golden
is the drift tripwire. (Same shape as `_generate_validate_fixture.py`; loads the real spaCy model,
asserted **hard**, never skipped — a missing model is a config error, and a skip would hide a
broken word-quality/NER port.)

**F4 — chat seam: minimal per-step, *not* the providers.py unification (BR-009 keeps that at M4c).**
triage and cleanup-LLM each get a minimal injectable chat seam — a `Protocol` co-located with the
step, defaulting to the real Anthropic client, injected via `run(..., chat=None)` — exactly
mirroring M4a's `Fetcher`/`OcrBackend`. Whether triage/cleanup/translate/refine *share* one
`ChatBackend` that M5's `providers.py` generalizes is **BR-009's open half, explicitly M4c's call**
(it needs all the chat consumers in front of it). M4b does not pre-decide it; two small per-step
seams now is the same "siblings, not a premature unification" logic M4a used.

**F5 — `flagged_segments.json` vs `review_flags.json` (don't conflate).** triage reads
`flagged_segments.json` (reconcile's word-disagreement output; the golden fixture
`flagged_segments_expected.json` confirms reconcile produces it). cleanup's *own* sidecar is
`review_flags.json` (unresolved hyphens/stray symbols), which adjudicate consumes. Different files,
different producers — the port keeps them distinct.

**F6 — triage mutates `reconciled_chapters.json` in place; cleanup reads it.** triage applies
accepted resolutions back into `reconciled_chapters.json` (`_apply_resolutions`, atomic write). It
is **not** regen-guarded (BR-012 names cleanup + translate/refine only): the mutation is
find-first-occurrence replace, effectively idempotent (a second run finds the already-replaced word
gone), and `reconciled_chapters.json` is reconcile-reproducible, not hand-tuned. In the engine this
is `work/data/reconciled_chapters.json`, never the frozen golden input — no golden conflict.

**F7 — `utils.py` dependencies the live code imports.** Live triage/cleanup import
`retry_api_call`, `atomic_write_json` from `utils`. The engine already has `util.jsonio`
(`atomic_write_json`/`atomic_write_text`/`read_json`). `retry_api_call` (backoff on API calls) has
no engine home yet → port a minimal `util.retry` (or fold into the chat seam's default impl).
**No new third-party dependency** — `anthropic` is already declared (M4a's ocr uses Gemini;
triage/cleanup-LLM use Anthropic, also already in `pyproject.toml` for the existing pipeline). Verify
at port time.

---

## 4. `triage` port

**Language-neutral mechanics → `steps/triage.py`** (port ~verbatim): the needs-triage filter
(`resolution_method in {all_differ, score_heuristic}`), the batch loop, `_is_plausible_correction`
(SequenceMatcher ≥ 0.4), the three resolution passes (auto-accept / needs-human / low-confidence),
and `_apply_resolutions` (group-by-(chapter,paragraph), first-uncorrected-occurrence replace).
Outputs `triage_review.json` + `triage_resolved.json` into `ws.data`, mutates
`ws.data/reconciled_chapters.json`. `_is_plausible_correction` + `_apply_resolutions` are pure →
unit-tested directly.

**Taxonomy → code default (BR-011).** `CATEGORIES` (the 7-member enum) + the `classify_disagreement`
tool schema are module constants in `steps/triage.py` — settled general engine logic, not config.

**Prompt → template.** `TRIAGE_SYSTEM` → `profiles/prompts/triage.txt.j2`, rendered with
`build_prompt_context(cfg)` (book facts + `{{ language.* }}`) **plus** witness descriptions. Witness
labels come from `manifest.sources[].label` (copy1/copy2) + a copy3 description derived from the
`ocr` model role (BR-011's "witness descriptions → `manifest.sources[].label` + the ocr-produced
copy3"). The Italian/Bodoni *example patterns* in the live prompt (`e↔c`, `ii→u`, accento
facoltativo) are `source_noise` + language facts → rendered into the template, not baked. *(Open:
exactly which example patterns are book-neutral-with-config-values vs. PLL-illustrative prose —
decided at porting against the rendered output; the leakage test (below) is the backstop.)*

**Chat seam (F4).** `class Chat(Protocol): def classify(self, *, system, tool, messages) -> list[dict]`
(or a thinner `create(...)` mirroring the live `messages.create` tool-use call), default
`AnthropicChat` (model `claude-sonnet-4-6`, the live id), injected via `run(..., chat=None)`. Tests
inject a fake returning canned `classify_disagreement` inputs.

**Tiers:** property (plausibility check; resolution passes map triage verdicts → resolutions
correctly; `_apply_resolutions` replaces the right occurrence and is idempotent on re-run) +
separability (runs the **synthetic** book's `flagged_segments.json` with an injected chat → writes
triage outputs + mutates the synthetic `reconciled_chapters.json`; **prompt leakage** render test:
no PLL strings leak from `triage.txt.j2` under the synthetic context, same assertion shape as
`test_no_pll_string_leaks_under_synthetic_render`) + isolation (the five live trees unchanged). **No
equivalence golden** (LLM) — recorded.

---

## 5. `cleanup` port

### 5a. Deterministic core (golden, D4)

**Algorithms stay in `steps/cleanup.py`** (language-neutral *code*): `is_noise_line`,
`dehyphenate_token`/`dehyphenate_text` (multi-pass), `normalize_punctuation`,
`join_broken_paragraphs`, `deduplicate_sentences`, `apply_dictionary_correction` (symspell + spaCy
NER orchestration), the inline artifact/asterisk/spacing fixes in `clean_text`, and the flag
emitters (stray-symbol, f-ligature, paragraph-initial-lowercase). The **data they parameterize on**
moves to config/lang per F2 + M4b-D1.

**Config bindings:**
- frequency dict / spaCy NER / symspell → the three lazy module singletons
  (`_get_word_set`/`_get_ner_nlp`/`_get_spellchecker`) are **deleted** and routed to the engine's
  shared path-keyed loaders (M4b-D4, LOCKED): `dictionaries.frequency.load_word_set` (built
  anticipating cleanup) + `lang.load_spacy` (validate's call) + a new
  `dictionaries.symspell.load_symspell` (path-keyed, mirrors `frequency.py`). Path-keying satisfies
  the framework plan's anti-collision intent without cleanup-local module state.
- `source_noise.substitution_rules` / `boundary_substitutions` ✓ (reuse, as adjudicate does);
  **new** `source_noise.noise_line_pattern` (§6); the inline page-marker regexes join the existing
  `page_marker_artifact_pattern` family.
- Italian accent/vowel data → language layer (M4b-D1).

**Oracle reuse (F6 of the M4 plan).** cleanup's LLM path builds Zingarelli context from flagged
tokens. adjudicate **already ported** `DictionaryOracle.lookup` + `dictionary_context_for_flags`
"specifically so cleanup can reuse them." cleanup imports them from `steps.adjudicate` and binds the
oracle via the same `_build_oracle(cfg)` (monolingual period dict) — no re-derivation. (M6 swaps the
oracle for ≥2-of-N without touching cleanup, BR-001.)

**Golden (D4):**
- Generator `tests/golden/_generate_cleanup_fixture.py` (dev-only, leading underscore): imports the
  **live** `cleanup`, runs `cleanup(use_llm=False)` over frozen
  `reconciled_chapters.json` + `chapter_pages.json` (no `corrections.json`) in a temp dir →
  `tests/golden/data/italian_clean_detcore_expected.md`; asserts the live tree reachable; writes
  only into `tests/golden/data` (+ freezes `chapter_pages.json` into `books/.../inputs` if not
  already present — `chapter_start_pages.json` exists; confirm the cleanup-consumed
  `chapter_pages.json` shape at port time).
- Test `tests/golden/test_cleanup_golden.py` (marker `golden`): seed the workspace with the frozen
  inputs, run engine `cleanup(use_llm=False)` → assert `ws.output/italian_clean.md` byte-equals the
  expected; assert it landed in the workspace, never the live tree. Loads real spaCy + symspell,
  asserted hard. *(Inputs to freeze: `reconciled_chapters.json` (frozen) + `chapter_pages.json`.
  Verified: engine `reconcile` **produces** `chapter_pages.json` — short ids, `{id: [pages]}`,
  `reconcile.py:48,705` — which is exactly cleanup's shape; the `inputs/` dir currently freezes only
  `chapter_start_pages.json`, the **separate** `parse_md`-keyed sidecar, not this. So the generator
  freezes reconcile's `chapter_pages.json` output (or omits it → no page markers).)*
- **Anti-cheat (I3/§5):** the expected values come from the independent live implementation. Any
  later change to them needs a `DL`/`RF` entry (none expected — this is a faithful port).

### 5b. LLM-correction path (property only)

Port `llm_correct_italian` (sync per-chapter), `_build_user_content`, `_strip_preamble`/`_PREAMBLE_RE`,
`extract_corrections_from_diff`, `apply_corrections`, and the **Batch API** path
(`_build_batch_requests`/`submit_batch`/`poll_and_collect_batch`) — all through the F4 chat seam
(the Batch path needs the seam to expose batch submit/poll, or stays a thin default-only method with
the property tier covering the deterministic request-building). `_LLM_CORRECT_SYSTEM` →
`profiles/prompts/cleanup_correct.txt.j2` (book + language facts; the Zingarelli reference block is
appended from the oracle). Full-text cache → `ws.state/llm_cleaned/{ch}.txt`; batch state →
`ws.state/llm_batch.json` (matching live `state/` placement; both transient).

**Post-LLM flag bookkeeping → ported here (M4b-D5).** `reconcile_flags` (`:1459`, deterministic, no
LLM) follows the LLM pass (`pipeline.py:247`, gated on `--llm-cleanup`): it diffs the pre-LLM
`review_flags.json` against the corrected `ws.output/italian_clean.md` and writes the flags whose
`context`/`token` still appears to `ws.data/review_flags_remaining.json` (atomic, via the engine's
`atomic_write_json`). `review_flags.json` is preserved intact. Unit-tested directly (property tier).

**Multi-witness flag-review duo → M5 (M4b-D5, out of scope above).**

**Tiers:** property (request-building from chapters/flags; `_strip_preamble` strips known preambles
and nothing else; `extract_corrections_from_diff` round-trips; `apply_corrections` applies +
suppresses resolved flags + drops stale flags; cache-precedence: a present `llm_cleaned/{ch}.txt`
wins over `clean_text` output; `reconcile_flags` keeps only flags whose `context`/`token` still
appears in the corrected output and preserves the original sidecar) + separability (synthetic book
end-to-end with injected chat; prompt leakage render test) + isolation. **No equivalence golden** for
this path (LLM).

### 5c. Regen-guard (BR-012, §2)

`cleanup.run` checks `ws.output/italian_clean.md` at top-of-run; if present and `allow_regen` is
false → `RegenerationGuardError`. Override per M4b-D2.

---

## 6. New config — `source_noise.noise_line_pattern`

models.py's `SourceNoiseProfile` docstring reserved this for "M4b (cleanup) — its only consumer".
M4b adds it: the field, the schema entry (`source_noise.schema.json`), the loader builder line, and
the value in `bodoni_didone.json` (the verbatim `NOISE_LINE_PATTERN` body, `:14-16`) **and** the
synthetic profile (synthetic uses `bodoni_didone`, so it inherits it — confirm both books validate).
This closes one of I10's named forward-reservations (`source_noise` field → M4b). The f-ligature
table (`_FLIG_SUBS`) home is M4b-D3.

---

## 7. Decisions (recommendations; please rule per point)

**M4b-D1 — where Italian accent/vowel data lives. LOCKED (2026-06-23): fully into the config
layer.** The data ports **verbatim** (no NFKD swap: `util.text.strip_accents` (NFKD) is *not*
byte-equivalent to the live fixed `_ACCENT_MAP` on non-Italian glyphs like `ç`/`ñ`, which a foreign
name could surface → golden risk). The home is the **language profile (config)**, not a plugin
method — matching how the engine already keeps language accent *data* in the profile
(`accent_inventory`, `word_score_accents`, `coverage.letters`) and reserves the plugin for
*behavior*:
- **Fold map** → a new `accent_fold` profile field (parallel `from`/`to` strings → `str.maketrans`,
  the verbatim live table); the fold *mechanics* (`str.translate`) → a generic `util.text` helper.
- **Restrictive accented-letter char-classes** (the `:231`-style enumerations) → **one presumed
  canonical superset** field, used at every site, **golden-validated**. The superset only ever
  *adds* characters to a site's class, so a behavioral change shows up as a red detcore golden
  naming the site → resolve faithfully (revert that site) or license a `DL` (only with ground truth
  the superset is *more* correct), **never silent acceptance** (I3). Zero red sites expected (the
  per-site inconsistencies sit in edge cases 1913 Italian prose doesn't hit), but the golden makes
  "expected" safe to act on. *Field identity (two-way door, settled at porting):* a dedicated
  `accented_letters` field (recommended — matches the engine's purpose-separated accent-field
  discipline, avoids coupling cleanup to validate's `coverage.letters` allowlist) vs. reuse
  `coverage.letters` (lighter).
- **Redundant `:486` clause** → neutral `.islower()` (covers all six accented vowels — verified).
- **`[À-ÿ]` ranges** (`:83`, the punct/word regexes) → a new **`word_letter_class`** language-profile
  field (the permissive "any word letter" class cleanup's tokenization regexes use). This is a
  *script* fact, **not** neutral code — a non-Latin book needs a different class. It does **not**
  reuse `coverage.letters`: verified against the frozen text, the range matches `ó` (U+00F3,
  *present*) which the restrictive allowlist excludes, so narrowing would change tokenization. The
  superset-vs-allowlist split is now empirically pinned — the only char `coverage.letters` adds over
  the live enumerations is `É`, **absent** from the text, so the D1-T3 unification is golden-safe;
  the range, conversely, genuinely needs its own field. *Representation (porting two-way door):* a
  regex char-class fragment (`"a-zA-ZÀ-ÿ"`) — a documented exception to `CoverageSpec`'s no-regex
  rule (its consumer is compiled regexes, not a membership set) — or structured range-data
  (`[["À","ÿ"]]`) + a small builder to keep config regex-free. Lean fragment + clear docstring.
- **adjudicate's identical in-step `_ACCENT_MAP`** reconciles to the same `accent_fold` source (no
  equivalence golden there — branch-unit-tested — so the move is low-risk and removes the sibling
  wart rather than leaving it).
- **Proof:** I4 core-neutrality scan **+** a new unit test asserting **no Italian character literal
  survives in `steps/cleanup.py`** (all sets sourced from `cfg`/`lang`).

**M4b-D2 — regen-guard override form (BR-012). LOCKED (b) (2026-06-23):** `allow_regen` kwarg +
global env `ENGINE_ALLOW_REGEN=1`, **no CLI flag** (future-need-only; discoverability via the error
message). Refusal as typed `RegenerationGuardError` (new `EngineError`, exit 6). Reused unchanged by
`cleanup`'s LLM path and, at M4c, by `translate`/`refine`.

**M4b-D3 — f-ligature table home. LOCKED: config (2026-06-23).** `_FLIG_SUBS` (`u→fi`, `tt→ff`, …) is
a *typeface ligature confusion* (Bodoni `fi`/`fl`/`ff` ligatures misread), the same *kind* as
`boundary_substitutions` (language-neutral, dictionary-validated char-confusion). → a **new
`source_noise.ligature_substitutions` field**, **schema-required** with explicit `[]` for a profile
without it (BR-004 required-and-explicit discipline, not silent-default), verbatim `_FLIG_SUBS` for
`bodoni_didone`. A **separate** field from `boundary_substitutions`/`substitution_rules` (three
distinct mechanisms — don't over-unify). This is **placement** (into the per-typeface `source_noise`
home, alongside the others), **not** the deferred BR-007 cross-typeface *layering* — that stays
deferred (no 2nd typeface). The advisory-only nature ("just review flags") does not earn an
exception from D1's no-typeface-literal-in-step rule.

**M4b-D4 — cleanup's three resource globals. LOCKED (2026-06-23): reuse the engine's shared
path-keyed loaders** (supersedes the plan's re-key-vs-instance framing — the engine already decided
this, and `frequency.py` was built anticipating cleanup). Process-wide cache keyed by resolved
path/model-name, built from `cfg`:
- `_get_word_set` → **delete**; reuse
  `dictionaries.frequency.load_word_set(require_asset(cfg.language.frequency_dictionary))` (docstring
  already names cleanup as the second consumer; `_WORD_SETS` path-keyed cache).
- `_get_ner_nlp` → **delete**; reuse
  `lang.load_spacy(cfg.language.spacy_model, disable=["parser","lemmatizer"])` (validate's exact
  call, `validate.py:431`).
- `_get_spellchecker` → **delete**; add `dictionaries/symspell.py::load_symspell(path)` — the one
  resource with no engine home (validate doesn't use symspell); path-keyed cache mirroring
  `frequency.py`; SymSpell tuning (edit-distance 2, prefix 7) a code default in the loader.

Path-keying is *finer* than the framework plan's "re-key by language id" and satisfies its
anti-collision intent; the heavy loads stay once-per-process (test-suite speed). `word_set` remains
the injectable `clean_text(text, word_set=None)` param for fast property tests; the symspell/NER path
is golden-covered.

**M4b-D5 — the multi-witness flag-review duo → M5; `reconcile_flags` → M4b. LOCKED (2026-06-23).**
Two findings, verified against the live tree:
- **Duo excluded → M5.** `llm_fix_flagged_tokens` (`:1058`) + its `_call_claude_flags` (`:1006`) /
  `_call_gemini_flags` (`:1031`) callers + `_build_flag_entries`/`_parse_flag_responses` +
  `_FLAG_REVIEW_SYSTEM` are a *self-contained cluster with no caller*: `llm_fix_flagged_tokens`
  appears only at its own definition, the two flag-callers fire only from inside it, and
  `pipeline.py` invokes `cleanup()` + `reconcile_flags()` — never `llm_fix_flagged_tokens`. So it is
  excluded for **two independent reasons**: (a) it is the multi-witness family (second provider +
  Claude/Gemini agreement), which BR-009 holds at M5; (b) it is not wired into the cleanup step or
  the pipeline at all, so dropping it from M4b is **behavior-neutral**. M5 decides whether it is
  worth porting or is dead code.
- **`reconcile_flags` included → M4b** (a scope item the earlier draft under-specified).
  `reconcile_flags` (`:1459`) **is** wired (`pipeline.py:247`, gated on `--llm-cleanup`), is
  **deterministic** (no LLM — substring-containment of each flag's `context`/`token` against the
  post-LLM `italian_clean.md`; surviving flags → `review_flags_remaining.json`, atomic), and is the
  bookkeeping that *follows* the single-model LLM pass M4b ports. It belongs in §5b — a pure helper,
  unit-tested directly. Not the duo; a separate, single-purpose function that merely shares the file.

---

## 8. Branch-register entries M4b opens / resolves

- **BR-002** — disposition recorded: code-neutrality half resolved at M4b (refactor + new unit
  test + I4 scan); full non-Italian fixture re-deferred to M7. *(update existing entry)*
- **BR-006** — re-read recorded: cleanup is not a consumer; re-deferred (translate is, M4c).
  *(update existing entry)*
- **BR-007** — sharpening recorded: placement already resolved (both tables config-resident);
  only cross-typeface layering re-deferred. *(update existing entry)*
- **BR-012** — resolved at M4b for cleanup: detection-based refusal + override form (M4b-D2);
  reused by M4c. *(update existing entry)*
- **BR-014 (new)** — chat seam at M4b: minimal per-step injectable `Chat` seams (triage,
  cleanup-LLM), defaulting to Anthropic; the providers.py-unification half stays BR-009/M4c. *(new,
  the M4b sibling of BR-009)*
- **BR-013** — cleanup's deterministic output is a new entry in the `inputs/` fixture-lifecycle
  ledger: the detcore golden's frozen inputs (`reconciled_chapters.json`, `chapter_pages.json`) and
  the per-producer keep-or-retire note. *(append to existing entry)*

## 9. Invariant controls folded into M4b (from `invariants.md`)

- **I9** — the run-twice-under-different-`PYTHONHASHSEED` idempotency test (currently inspection-only)
  is **built here**, covering the new deterministic surfaces (`cleanup` detcore + triage's pure
  resolution logic) alongside the existing reconcile/adjudicate/validate set.
- **I6** — the mechanizable doc-ref sliver (assert every doc-cited test name resolves; no stale
  scrubbed terms) is **built here** as a test.
- **I3/I5/I7/I8** — the new step inherits the standing controls: detcore golden (I3), no re-spelled
  wire literals (I5), isolation snapshot (I7), atomic writes only — no raw `write_text` under
  `steps/` (I8; note the live cleanup uses raw `write_text` for the cache + output — the port must
  route through `atomic_write_text`).

## 10. Done when

- `triage` passes **property + separability + isolation** (no golden); `cleanup` passes
  **equivalence (detcore golden) + property + separability + isolation** (D4).
- The detcore golden reproduces the live `cleanup(use_llm=False)` byte-for-byte.
- cleanup's step code holds **no** Italian literal (M4b-D1); the new neutrality unit test + I4 scan
  pass; `steps/cleanup.py` and `steps/triage.py` pass I8 (atomic writes only).
- Two prompt-leakage render tests pass (triage + cleanup-correct templates, synthetic context).
- The regen-guard refuses a re-run that would clobber `work/output/italian_clean.md` without the
  override (negative control), and allows it with the override (positive control).
- I9 run-twice + I6 doc-ref tests are built and green.
- New config (`source_noise.noise_line_pattern`, + M4b-D3) validates for both books; loader + model
  + schema updated.
- Branch register + invariants log updated (§8/§9). Full suite green from `engine/`:
  `cd engine && uv run pytest`.

---

## 11. In-flight port progress + refinements (recorded for continuity, 2026-06-23)

**Committed on `engine-framework` (full suite 190 green throughout):**
- `ea0c3c7` — **triage** ported: `steps/triage.py` (injectable `Chat` seam BR-014; `CATEGORIES` +
  tool schema as code defaults BR-011), `profiles/prompts/triage.txt.j2`, `util/retry.py`, synthetic
  `flagged_segments.json`, `test_triage_engine.py` + isolation. Tiers: property + separability +
  leakage + isolation (no golden — LLM). The prompt **drops the live Italian confusion *example
  words*** (`più`, `pàtria`): they'd render under the Italian-profiled synthetic book and trip the
  no-Italian-leak render test; the category set + witnesses + the `accent_optional`-gated rule carry
  the guidance.
- `10cceeb` — cleanup **config foundation**: `language.accent_fold` / `accented_letters` /
  `word_letter_class`; `source_noise.noise_line_pattern` / `ligature_substitutions`;
  `dictionaries/symspell.py` (D4 loader); `util.text.build_fold_table`. All byte-match live.
- `368c308` — `word_letter_class` sourced from config in **validate + adjudicate** (was inline
  `À-ÿ`); both goldens green. `74a7175` — adjudicate `_ACCENT_MAP` → `cfg.language.accent_fold`
  (oracle-held), identical on all exercised data.

**Refinements decided during the port — honor these in the cleanup-core write:**
1. **Detcore golden = `clean_text` per chapter** (`{id: {text, flags}}`), NOT the full wrapped
   `.md`. The wrapper bakes book identity inconsistent with config (`# Per la Libertà!` cap-L vs
   `edition.title_it` `Per la libertà!`); isolating the algorithm keeps the equivalence check honest
   and sidesteps freezing `chapter_pages.json`. Wrapper = config-driven + property-tested. I3
   anti-cheat preserved (expected values come from the live `clean_text`).
2. **Chapter sort = stable on the existing `ch["part"]` field**, not id parsing — synthetic uses
   long ids (`p1_capitolo_primo`), PLL short (`p1_ch01`); the live `chapter_sort_key` crashes on
   long ids.
3. **Markdown wrapper from config**: `# {edition.title_it}`, `*{edition.subtitle_it}*`,
   `**{edition.author}**`; part headers from `structure.parts[N-1].name` (part 2 gets a `---`
   separator); `part==0` chapter → `## {title}`, others → `### {title}`; page markers
   `<!-- pages:a-b -->` from `chapter_pages`.
4. **Source-noise relocations → `source_noise` config, in M4b (golden-guarded), not M7** — sharpens
   §10's done-criterion to **no Italian _or_ source-noise literal** in `steps/cleanup.py`:
   - `£→E` (`:575`) → `source_noise.char_substitutions` (list of `[regex, repl]`; bodoni:
     `[["£(?!\\d)", "E"]]`). Confirmed live source-noise: 17 `£` in source → 0 in output.
   - `:601-603` inline page-marker subs → `source_noise.inline_page_marker_patterns` (list).
   - `:241` compound noise class → `source_noise.page_marker_line_pattern` (str; the `len<30` /
     `≤1 real word` / `has-digit` guard stays in code).
   - `:14` `NOISE_LINE_PATTERN` + `:248` separator + `:251` `Disp.` furniture → a
     `source_noise.noise_line_patterns` **list** (match→noise). The committed singular
     `noise_line_pattern` folds into this list (restructure).
   - The real-word-recognition checks (`:231`, `:244`, `:257`) use `language.accented_letters` /
     `word_letter_class`; the noise-class accents ride along in `source_noise` as scan-garbage.
5. **D1 accent mechanics**: cleanup folds via `build_fold_table(cfg.language.accent_fold)` (NOT NFKD
   `strip_accents`). `:486` redundant `or first_char in "àèéìòù"` → `.islower()`. `:684` lowercase
   range → match `word_letter_class`, filter `.islower()` in the loop.
6. **D4 loaders**: delete `_get_word_set` / `_get_ner_nlp` / `_get_spellchecker` →
   `frequency.load_word_set` + `lang.load_spacy(disable=["parser","lemmatizer"])` +
   `symspell.load_symspell`.
7. **Oracle reuse (F6)**: import `DictionaryOracle` + `dictionary_context_for_flags` + `_build_oracle`
   from `steps.adjudicate`.
8. **LLM path**: single-model `llm_correct_italian` + Batch API via a per-step chat seam (BR-014);
   `_LLM_CORRECT_SYSTEM` → `profiles/prompts/cleanup_correct.txt.j2`; cache →
   `ws.state/llm_cleaned/{id}.txt`, batch → `ws.state/llm_batch.json`. `reconcile_flags` ported
   (deterministic, post-LLM bookkeeping, `--llm-cleanup`-gated). Multi-witness flag-review duo
   excluded → M5 (D5, verified orphaned).
9. **Regen-guard**: `RegenerationGuardError` (new `EngineError`, exit 6) + `allow_regen` kwarg +
   `ENGINE_ALLOW_REGEN` env (D2); top-of-run refusal to clobber an existing
   `ws.output/italian_clean.md`.
10. **Neutrality test** scans `cleanup.py` for *functional* Italian/source-noise literals — must
    exclude docstrings/comments, which legitimately *name* `À-ÿ` etc. when describing the change.

**Next:** write `steps/cleanup.py` (deterministic core + wrapper) + the source_noise config additions
(§4 above) + the detcore golden generator/test + the neutrality test, as one unit so the golden
validates every relocation on arrival; then the LLM path + reconcile_flags; then the regen-guard.
