# Documentation Audit — Run 1 vs Run 2 Comparison

*Companion to [`DOC-AUDIT.md`](DOC-AUDIT.md) (Run 1) and [`DOC-AUDIT-2.md`](DOC-AUDIT-2.md) (Run 2).*

Two independent multi-agent documentation audits were run against the same doc set
(`CLAUDE.md`, `README.md`, `PIPELINE.md`, `REVIEW.md` primary; `1913-italian-ocr-normalization-reference.md`,
`dictionary-agent_prompts.md` reference). Run 2 was run "clean" — without the Run 1 results in the
project or in agent context — to avoid contamination, then the two were compared.

This is a **semantic** comparison, not a textual diff (the two artifacts use different finding ids,
ordering, and prose). It records where the runs **converge** (high-confidence findings), where each
run had **blind spots** the other caught, and the one substantive **disagreement**. Like the source
artifacts, this is audit-only: nothing here changes any doc.

Resolved findings that no longer apply to the codebase have been pruned from this artifact.
Convergent core ≈ 24 findings; each run surfaced ~6–8 *material* items the other missed entirely.

---

## 1. Convergent core — both runs found it

Highest-confidence findings: independently surfaced by both runs. Triage these first.

| # | Finding | Run 1 | Run 2 |
|---|---------|-------|-------|
| C1 | LLM-cleanup cache described three contradictory ways (CLAUDE.md "empty" vs `pipeline.py` "31/58" vs "all 58 corrected"); dir absent on disk | §1/§3 (multiple) | S1 / A1 |
| C2 | README deploy `cp` block clobbers typeset's path-rewritten `docs/` auto-sync | §1 High (CSS) + Low + cross-cut | S11 / A2 / G-readme-deploy |
| C3 | `cd docs && git add -A` stages the whole tree, not just the site | cross-cutting note | A-gitaddall |
| C4 | `README.md:151` cites the wrong IA identifier (`…cresuoft` vs code's `…cresgoog`) | §1 Med + §5 High | S13 / P-ia-ids |
| C5 | `1913-italian-ocr-normalization-reference.md` names the wrong project ("the Athanor pipeline") | §1 Low + §3 Low + §5 Med | S-norm-athanor |
| C6 | `dictionary-agent_prompts.md` prescribes unshipped libs (diff-match-patch, minineedle, unidecode, collatex) | §1 Low + §2 Low | S-dict1 / S-dict2 / S-dict3 |
| C7 | `dictionary-agent_prompts.md` prescribes `it_core_news_sm`; code uses `it_core_news_lg` | §3 Low | S-dict6 / S-dict7 |
| C8 | Reference docs are pre-implementation design briefs with no "superseded" banner | §1/§2 Low | A-dict-status |
| C9 | LOC source PDF required, gitignored, undocumented as a prerequisite | §2 Med | G-readme-ocrpdf |
| C10 | Harvard PDF required for second-copy escalation, never listed as a prerequisite | §2 Med | G-readme-harvard-pdf |
| C11 | Review-phase API keys (`OPENAI_API_KEY`, `DEEPL_API_KEY`) absent from README `.env` | §2 Med | G-readme-openai-env (partial — frames OPENAI as optional) |
| C12 | `serve.py` invocation style / `PORT` / what it serves | §1 Low | G-claude-serve / A-serve-docs |
| C13 | Track 6 documented as bare `python …`, contradicting the `uv run` rule | §3 Med + Low | A-track6-uvrun |
| C14 | `fix_corrupted_passage.py` missing from REVIEW.md's dead-script list | §2 Low | G-rev-deadscript |
| C15 | "calibrated" (REVIEW.md:156) asserted with only scale counts as evidence | §4 Med | T-comprehension-calibrated |
| C16 | "best vision of the current crop" — unsubstantiated/time-bound superlative | §4 Med | P-vision-model (reframed as transient pin) |
| C17 | Bodoni `i→r`/`i→e` boundary substitutions are typeface-specific (portability) | §5 High | P-dehyphenate |
| C18 | Italian chapter-title ordinal maps hard-coded (portability) | §5 High | P-titles |
| C19 | Pinned Italian dictionary trio + oracle is language/era-specific (portability) | §5 Med | G-dict-oracle (reframed as gap) |
| C20 | Review phase presupposes two specific physical copies + concordance (portability) | §5 Med | P-panel-models / G-readme-harvard-pdf |
| C21 | Zingarelli has no auto-download path (README "downloaded automatically" overstates) | cross-cutting note | A-dict-membership / README:120 note |
| C22 | Pipeline step-count headline: 9 (table) vs 11 (prose) | cross-cutting note | A-11step |
| C23 | Two chapter-id schemes (`p1_ch18` vs slug) hidden behind one placeholder / the "slug" wording | §3 Low (slug, two schemes) | A-slug / A-chapter-schemes (rated High) |
| C24 | Book-identity hard-coded into translation prompt(s) (portability) | §5 High (`translate.py` SYSTEM_PROMPT) | P-multiwitness-rubric (`multi_translate.py` rubric — related, different site) |

Note on severity: C23 is a useful calibration check — Run 1 rated the chapter-id ambiguity **Low**;
Run 2 rated it **High**. Run 2's verifier downgraded the "wrong-id harm" claim to needs_nuance but
kept the finding, so the true severity is probably **Medium**.

---

## 2. Run 1 found — Run 2 missed (Run 2 blind spots)

Ordered by consequence.

- **R1-a — The `claude` Claude Code CLI dependency for multi-model synthesis.** *(Material.)*
  Synthesis shells out to `claude -p …` via `subprocess` (`multi_translate.py:507-523`), requiring the
  CLI on PATH — which `uv sync` does not provide — and using the CLI alias `opus`, not an API model id.
  A user with valid keys but no CLI cannot reproduce the live edition. Run 2 documented `--multi-model`
  flags but never this hard dependency.
- **R1-b — The reading edition defaults to single-language, not facing pages.** *(Material; branch-relevant.)*
  `typeset.py:173` defaults language focus to English-only with a Both/IT/EN toggle; facing-page is
  opt-in. All three docs describe "Loeb-style facing pages" unconditionally. Run 2 missed this entirely.
- **R1-c — `chapter_count` hard-coded as 58 in `validate.py`.** Both the doc ambiguity (58 vs the
  57 H3 + ≥3 H2 actually checked) and the portability angle (chapter total / part split as constants).
  Run 2 has **neither**.
- **R1-d — Bibliographic metadata hard-coded in `typeset.py`** (title/subtitle/author/colophon,
  `IA_ITEM_ID`). Portability. Run 2 isolated the source-scan page offset but not the colophon/identity constants.
- **R1-e — `assets/` directory comment is wrong** (`README.md:143`): fonts + LOC page images actually
  live under `docs/assets/`.
- **R1-f — `refine` shown inline in the build arrow-chain** despite being documented manual-only.
- **R1-g — Build-path model ids named** (evaluator `gemini-2.5-flash`, draft `gemini-2.5-pro`,
  default GPT `gpt-4o`) and the build-vs-review generation gap. Run 2's P-panel-models covers only the
  review-phase panel.
- **R1-h — Richer flattering-language catalog**: "validated", "zero/zero/zero", "authoritative",
  "honestly", "prime offender", "strong on / confidently", "one deliberate sweep". Run 2's tone
  section caught a different subset (workers "safely", long-s "Gemini claimed", "verified concerns").
- **R1-i — `--with-edgren` defaults off via `pipeline.py`** even though `multi_translate()`'s function
  default is True; and the **translate prompt's literal `*asterisk*` italics convention** that
  typeset's `*`→`<em>` conversion depends on.
- **R1-j — `crespi-1913-styleguide.html`** tracked at repo root, undocumented (Run 2 caught only the
  `fix_corrupted_passage.py` half of this finding).
- **R1-k — Stray-symbol set**: CLAUDE.md lists a subset of PIPELINE.md / code.

---

## 3. Run 2 found — Run 1 missed (Run 1 blind spots)

Ordered by consequence.

- **R2-a — The `audit_divergences.py` → `readjudicate.py` broken handoff.** *(Material.)*
  Writer emits `state/audit/divergence_candidates.json` (`audit_divergences.py:37,256`); reader reads
  `data/divergence_audit_candidates.json` (`readjudicate.py:33`). Both files exist at identical size
  (282 632 B), proving a **silent, undocumented manual copy/rename** in the Track-3 workflow. Run 1
  missed it entirely.
- **R2-b — Typography restoration is entirely undocumented in PIPELINE.md Step 8.** *(Material.)*
  `data/typography.json` via `typography.py` is a core part of typeset (loaded `:708-711`, applied to
  both languages `:955`/`:983`) and gets zero mention. Run 1 did not flag the Step-8 gap.
- **R2-c — Deeper reference-doc dissection** Run 1 skipped: the guillemets premise conflict
  (S-norm1), the `<ed1>/<ed2>` dual-reading scheme (S-dict5), two-vs-three witnesses in Prompt 1
  (S-dict8), and the wrong reconcile thresholds (80/60 vs actual `75`/`90`/`0.50`) (S-dict9).
- **R2-d — A whole layer of CLI-flag omissions**: `--local`/`--site-base`, `--draft-models`/
  `--synth-model`, the **`--chapter` scope asymmetry** (silently ignored by the single-model translate
  path), `--workers`, `--plan`, `--results`, `--ids`, `ocr --pages`, `mt --min-score/--top`,
  `box_crops --limit`, `context_judge --workers`, `--openai-api-key`. Run 1 largely skipped this.
- **R2-e — Conditional-output behavior**: missing `english_translation.md` → Italian-only edition
  (no error); `chapter_pages.json` written **only** in 3-way mode; `review_flags_remaining.json`
  omitted from Step 5 outputs; companion mirrors **all** non-md assets + syncs `docs/static/bilingual.css`.
- **R2-f — Concordance lifecycle ambiguity** (A-concordance-lifecycle): `fit` writes the draft
  (`verified=False`), `lock` flips it to `True` — the doc implies only `lock` writes.
- **R2-g — `1913-italian-ocr-normalization-reference.md` omits the Bodoni `i↔r`/`e↔i` confusion**
  (the repo's dominant OCR failure mode) while elevating f-ligature misreads (G-norm-ligatures).
- **R2-h — Python `>=3.13` requirement** unflagged in Setup (`.python-version` enforces it silently).
- **R2-i — GENERALIZABLE-BUT-HARDCODED isolation**: the source-scan page offset
  (`SCAN_LEAF_OFFSET=6`), the cluster-scoring weight formula (`8·breadth + 2·consistency + 6·severity + 1·confidence`),
  and pinned model ids — a portability tag Run 1 did not separate out.
- **R2-j — Italian structural keywords in `utils.py`** (PREFAZIONE/INDICE/Capitolo/PARTE SECONDA…)
  drive "generic heading detection" (P-structure-keywords). Related to Run 1's title finding but a
  distinct site.

---

## 4. Genuine disagreement

**The separate `spacy download it_core_news_lg` step** (README Setup):

- **Run 1** (§1 Low): *redundant — remove it.* `pyproject.toml` declares `it_core_news_lg` as a
  pinned wheel, so `uv sync` already installs it.
- **Run 2** (G-readme-python, needs_nuance): *arguably intentional — keep it.* The pin keeps
  `uv sync` from pruning a manually-downloaded model; call it conditional/explanatory, not a no-op.

**Run 2's reasoning is the correct one.** The pin and the explicit download are complementary, not
redundant; the doc fix is to *explain* the relationship, not delete the step.

---

## 5. Reading

- The **convergent core (§1)** is high-confidence; start triage there.
- Neither run dominates. Each had ~6–8 material blind spots the other caught — Run 1 owns the
  `claude`-CLI dependency and the single-language default; Run 2 owns the broken divergence handoff
  and the undocumented typography restoration. The **union** is meaningfully more complete than either
  alone, so triage should draw from both rather than picking a winner.
- Pattern in the blind spots: **Run 1** skewed toward whole-feature/architecture-level findings
  (CLI dependency, default layout, model generations) and a richer tone catalog; **Run 2** skewed
  toward operational/mechanical depth (CLI flags, conditional outputs, producer/consumer path
  mismatches) and finer portability tagging. The two are complementary lenses, not competing ones.
