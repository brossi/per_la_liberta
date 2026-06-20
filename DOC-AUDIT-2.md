# Documentation Audit 2 — Triage

*Audit-only artifact. No documentation was changed. All findings are verified audit results; stale/gap claims were verbatim-verified against the working-tree code and filesystem at audit time.*

## Executive Summary

64 findings.

By dimension:

| Dimension | Count |
|-----------|-------|
| Stale / Inaccurate | 14 |
| Gaps | 26 |
| Ambiguity | 14 |
| Tone | 4 |
| Portability / Book-Specific | 9 (1 also tagged GENERALIZABLE-BUT-HARDCODED under stale — see note) |

By severity:

| Severity | Count |
|----------|-------|
| High | 14 |
| Medium | 30 |
| Low | 20 |

Notes on counting and merges:
- The `state/llm_cleaned/` cache-state contradiction is reported by several near-identical findings across `CLAUDE.md:82`, `CLAUDE.md:276`, and the `pipeline.py:23,43` banner. These are consolidated below (see Stale §S1 and Ambiguity §A1) and counted once each where they were filed against distinct locations; the merges are called out inline.
- The `README.md:101-110` deploy-block defect was filed under both Stale (§S12) and Gaps (§G-merged) and under Ambiguity (§A); the three are the same underlying defect and are cross-referenced.
- The `README.md` "Project structure" omission was filed twice (gap §G and ambiguity §A); cross-referenced.
- The `README.md:120` / `README.md:151` dictionary-download and IA-identifier findings appear under multiple dimensions; cross-referenced.
- The "wrong Google/Harvard IA identifier" finding (`README.md:151`) appears both in Portability (`needs_nuance`, framed as portability) and in Stale (`confirmed`, framed as a wrong-id factual error). The Stale framing is the corrected one (see §S13 / Portability §P).

---

## 1. Stale / Inaccurate

### High

**S11 — `README.md:101-110` (Deploying to GitHub Pages)**
- Verbatim: the deploy snippet `cp output/bilingual.html docs/index.html` / `cp output/scan.html docs/scan.html` / `cp static/bilingual.css docs/static/bilingual.css` / `cd docs && git add -A && git commit -m "Update edition" && git push`.
- Problem: `typeset.py` already auto-syncs to `docs/` with path rewrites whenever `docs/` exists. `cp output/bilingual.html docs/index.html` is actively wrong: `output/bilingual.html` uses `../static/bilingual.css` and `../docs/assets/page_images`, while `docs/index.html` requires the rewritten `static/bilingual.css` and `assets/page_images` paths. Following the README literally breaks the deployed CSS and scan images.
- Triage: rewrite the deploy section to reflect that `--step typeset` already syncs `docs/` with path rewrites; the only remaining manual step is `git add/commit/push` from `docs/`. Remove the three `cp` commands (especially the `index.html` cp).
- Code evidence: `typeset.py:1598-1612` (auto-sync + `.replace` path rewrites + `shutil.copy2`); `output/bilingual.html` has 1× `../static/bilingual.css` and 58× `../docs/assets/page_images`, whereas `docs/index.html` has the rewritten `static/bilingual.css` and `assets/page_images`.
- (Merged: same defect as Gaps §G-merged and Ambiguity §A2.)

**S13 — `README.md:151` (Sources)**
- Verbatim: `- Google/Harvard scan: [archive.org/details/perlalibertdal00cresuoft](https://archive.org/details/perlalibertdal00cresuoft)`.
- Problem: the cited Internet-Archive identifier (`perlalibertdal00cresuoft`, a Toronto/uoft copy) is the wrong item. The pipeline downloads and depends on `perlalibertdall00cresgoog` (double-l, `goog` suffix). A reader following this link reaches a different physical copy than the edition was built and adjudicated against.
- Triage: change the URL to `https://archive.org/details/perlalibertdall00cresgoog` to match `download.py` / Copy B.
- Code evidence: `download.py:7` `COPY2_URL = ".../perlalibertdall00cresgoog/..."`; same id in `vision_review.py:41` and `build_concordance.py:37` (`harvard_perlalibertdall00cresgoog.pdf`); `perlalibertdal00cresuoft` appears nowhere in code. The LOC link on `README.md:150` is correct.
- Portability tag: BOOK-DATA. (Cross-ref Portability §P; the earlier portability framing of this line was corrected to this stale/wrong-id framing.)

**S-norm1 — `1913-italian-ocr-normalization-reference.md:15-19` (guillemets)** [needs_nuance]
- Verbatim: "**What to normalize:** Strip spaces between guillemets and their enclosed text. Normalize to `«Parola»` (no interior spaces) for consistency, or to your chosen quotation style if converting to a different convention."
- Problem: section 2's premise that «virgolette caporali» are the period convention to preserve contradicts this repo's code, which asserts guillemets are "not used in the 1913 original" and strips them to straight double quotes.
- Corrected claim: the conflict is specifically over whether guillemets are present in the source, not over the conversion action — line 19 itself permits converting to another style ("or to your chosen quotation style"). The doc is also a generic Athanor-targeted reference, so this is a doc/code factual mismatch rather than drift from this project's own spec.
- Triage: reconcile against `cleanup.py` — document that this book's pipeline converts «» to " (and why), or fix the code if guillemets should be preserved.
- Code evidence: `cleanup.py:321-325` strips `[«»]` → `"` ("not used in the 1913 original"); `output/italian_clean.md` has 1 guillemet vs 602 double-quote lines.

**S-dict1 — `dictionary-agent_prompts.md:15` (diff-match-patch)**
- Verbatim: "Use `diff-match-patch` (pip install diff-match-patch) as the primary alignment tool ... Use `diff_cleanupSemantic()` after every `diff_main()` call".
- Problem: the live reconciliation code does not use diff-match-patch at all; `reconcile.py` uses `difflib.SequenceMatcher.get_opcodes()` plus rapidfuzz. `diff-match-patch` appears nowhere in the codebase or `pyproject.toml`.
- Triage: mark the doc as an early design proposal (not the implementation), or rewrite to describe the shipped SequenceMatcher+rapidfuzz approach.
- Code evidence: `reconcile.py:6` `from difflib import SequenceMatcher`; `reconcile.py:188/361/425/434`; grep for `diff.match.patch` over `*.py`/`pyproject.toml` returns nothing.

**S-dict5 — `dictionary-agent_prompts.md:34` (`<ed1>/<ed2>` dual-reading tags)**
- Verbatim: "For edition differences: preserve both readings with simple XML-style tags: `<ed1>testo</ed1><ed2>testo</ed2>`. The downstream translation LLM is instructed to use the reading that best fits the grammatical and historical context".
- Problem: no `<ed1>/<ed2>` mechanism exists; `translate.py`'s prompt has no variant-selection instruction. The pipeline resolves witness disagreements at reconcile/triage into a single text, not via inline tags deferred to the translation LLM.
- Triage: remove the ed1/ed2 deferral scheme or mark it as rejected/unimplemented; document the actual triage-stage resolution.
- Code evidence: grep `<ed1|<ed2|ed1>|ed2>` over `*.py` returns nothing; `reconcile.py:474` "All three differ — use scoring, flag for triage".

### Medium

**S1 — `state/llm_cleaned/` cache state (merged across `CLAUDE.md:82`, `CLAUDE.md:276`, `pipeline.py:23,43`)**
- Verbatim (CLAUDE.md:276): "LLM cleanup via Batch API: all 58 chapters corrected, full-text cache in `state/llm_cleaned/`". Verbatim (CLAUDE.md:82): "The local LLM-cleanup cache (`state/llm_cleaned/`) is now empty, so `--step cleanup` would regenerate from scratch". Verbatim (pipeline.py:43 banner): "The local LLM-cleanup cache is incomplete (31/58) and ...".
- Problem: three-way disagreement on the state of `state/llm_cleaned/`. `pipeline.py`'s comment/banner say 31/58 and partly stale; `CLAUDE.md:82` says empty; `CLAUDE.md:276` says all 58 present. Ground truth: the directory does not exist in the working tree (`ls` returns "No such file or directory"); former contents are parked in `state/_llm_cleaned.stale-2026-04-03/` (31 files), both gitignored. All three counts are wrong; the `pipeline.py` banner is operator-facing text shown when the regeneration guard fires.
- `CLAUDE.md:276` is `needs_nuance`: the historical fact ("all 58 chapters were corrected" via Batch API) is true; the defect is the stale present-tense locative pointing at a path that no longer exists.
- Triage: pick one accurate description (incomplete/empty, directory moved aside) and use it consistently in the regeneration-guard section, Current Status, and `pipeline.py:23`/`:43`. Note the cache is transient and gitignored.
- Code evidence: `pipeline.py:22-24` comment; `pipeline.py:43` banner; `ls state/llm_cleaned/` absent; `state/_llm_cleaned.stale-2026-04-03/` = 31 files; `.gitignore:36-37`.
- Portability tag on the `pipeline.py:23,43` filing: BOOK-DATA.

**S-pdf — `CLAUDE.md:33, CLAUDE.md:215, CLAUDE.md:241; README.md:136` (PDF output)**
- Verbatim: "**PDF**: WeasyPrint (HTML→PDF). Render per-chapter then merge for performance (not yet implemented — currently single-pass)." plus the table "HTML/PDF", File-Structure `bilingual.pdf`, and README "Bilingual HTML/PDF generation".
- Problem: PDF generation is disabled in code; no `bilingual.pdf` is produced. "currently single-pass" implies it runs single-pass; it does not run at all. `PIPELINE.md` Step 8 Outputs already omits PDF, so the docs contradict each other.
- Triage: mark PDF as not-currently-generated (disabled pending `DYLD_FALLBACK_LIBRARY_PATH`); drop `bilingual.pdf` from step-8 outputs or annotate as not produced; reword `CLAUDE.md:215` so it doesn't imply PDF runs.
- Code evidence: `typeset.py:1614` disable comment + `generate_pdf()` call block (1616-1623) commented out; `ls output/` shows no `bilingual.pdf`; `PIPELINE.md:340` lists HTML/scan/css only.
- Portability tag: GENERALIZABLE-BUT-HARDCODED (the `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` constant).

**S-rev1 — `REVIEW.md:107` (`audit_divergences.py` output path)**
- Verbatim: the table row listing Outputs as "`data/divergence_audit_candidates.json`, `state/audit/report.md`".
- Problem: the script writes its candidate JSON to `state/audit/divergence_candidates.json` (different directory AND filename). The doc's stated output path is not a write target of the script. (`report.md` half is correct.)
- Corrected claim: `audit_divergences.py` writes its candidate JSON to `state/audit/divergence_candidates.json`, not `data/divergence_audit_candidates.json`.
- Triage: change the output cell to `state/audit/divergence_candidates.json, state/audit/report.md`. Separately reconcile the producer/consumer path mismatch (`readjudicate.py` reads `data/divergence_audit_candidates.json`).
- Code evidence: `audit_divergences.py:37` `AUDIT = state/audit`; `:256` write; `:284` report write; `readjudicate.py:33` reads the `data/` path. (Cross-ref Gaps §G-rev1: the same defect, escalated to High there because of the undocumented manual copy/rename handoff.)

**S-norm-athanor — `1913-italian-ocr-normalization-reference.md:3` (wrong pipeline named)**
- Verbatim: "Use this as a reference when building or refining punctuation/normalization passes in the Athanor pipeline."
- Problem: the doc lives in and describes the Per la Libertà repo but instructs the reader to apply it to "the Athanor pipeline," a different project for a different book (The Kybalion). A contributor would look in the wrong place.
- Triage: re-target to "the Per la Libertà cleanup pipeline (`cleanup.py`)" or drop the named-pipeline reference.
- Code evidence: `CLAUDE.md:288` (Athanor is `~/LLM/Athanor`, The Kybalion); only other Athanor mention is `triage.py:3` ("Adapted from Athanor's..."); no Athanor pipeline in this tree.

**S-dict2 — `dictionary-agent_prompts.md:17` (minineedle / Smith-Waterman)**
- Verbatim: "fall back to Smith-Waterman local alignment. The `minineedle` package (pip install minineedle) implements this for arbitrary Python iterables".
- Problem: `minineedle` is not a dependency and is used nowhere; no Smith-Waterman fallback exists. `reconcile.py` handles structural divergence via SequenceMatcher opcodes and a chapter-length-ratio split estimate.
- Triage: remove or relabel as unimplemented design idea.
- Code evidence: grep `minineedle` over `*.py`/`pyproject.toml` returns nothing; `reconcile.py:138`.

**S-dict3 — `dictionary-agent_prompts.md:13` (unidecode)** [needs_nuance]
- Verbatim: "*Diacritic folding for comparison:* Use `unidecode` to create a comparison-only copy of each text where `ò`, `o'`, and `ó` all reduce to `o`."
- Problem: `unidecode` is not a dependency and is unused; `reconcile.py` folds via `unicodedata`.
- Corrected claim: `dictionary-agent_prompts.md` is a recommended-technique prompt doc, not implementation docs. Line 13 recommends `unidecode`; line 40 recommends an entire stack (`diff-match-patch rapidfuzz minineedle spacy unidecode`, plus collatex) — none of unidecode/diff-match-patch/minineedle/collatex/rapidfuzz are present except rapidfuzz. The actual `reconcile.py` uses `difflib.SequenceMatcher` + `unicodedata`. So the doc recommends a tooling stack the implementation never adopted; unidecode-vs-unicodedata is one instance, not an isolated stale line.
- Triage: replace `unidecode` with the actual (`unicodedata`-based) normalization or mark as design-only.
- Code evidence: grep `unidecode` over `*.py`/`pyproject.toml` returns nothing; `reconcile.py:5` `import unicodedata`; `pyproject.toml` lists only rapidfuzz among the named libs.

**S-dict6 — `dictionary-agent_prompts.md:41` (`it_core_news_sm` install)**
- Verbatim: `python -m spacy download it_core_news_sm`.
- Problem: the repo uses `it_core_news_lg`, not `it_core_news_sm`. The wrong model name also appears at lines 69, 75, 122.
- Triage: change `it_core_news_sm` → `it_core_news_lg` at lines 41, 69, 75, 122 (or note the doc predates the lg upgrade).
- Code evidence: `edgren.py:57` `spacy.load("it_core_news_lg")`; `pyproject.toml:13` pins `it_core_news_lg-3.8.0`; grep `it_core_news_sm` over `*.py` returns nothing.

**S-dict7 — `dictionary-agent_prompts.md:75` (`it_core_news_sm` snippet)** [needs_nuance]
- Verbatim: `nlp = spacy.load("it_core_news_sm")`.
- Problem: the sample snippet loads the small model.
- Corrected claim: the file is a self-contained agent build-brief, not documentation of `edgren.py`, and it consistently specifies `it_core_news_sm` in its own install lines (41, 122), prose (69), and code (75). The defect is project-wide model inconsistency: the brief standardizes on `_sm` while the project installs ONLY `_lg`. The snippet's `lookup_1901` function does not exist in `edgren.py`.
- Triage: update snippet to `it_core_news_lg` (and reconcile the whole brief).
- Code evidence: `edgren.py:57`; `pyproject.toml:13`; `README.md:32` / `CLAUDE.md:41` both `download it_core_news_lg`.

**S-dict8 — `dictionary-agent_prompts.md:7` (two vs three witnesses)**
- Verbatim: "We have two OCR text files of the same vintage Italian book ... aligning and reconciling the two versions."
- Problem: the live pipeline reconciles THREE OCR witnesses (Copy 1, Copy 2, Copy 3 = Gemini Pro vision as word-level adjudicator). Prompt 1 is framed as a 2-witness problem, materially understating the collation architecture.
- Triage: update Prompt 1 to a three-witness model, or mark as a pre-Copy-3 design snapshot.
- Code evidence: `reconcile.py:408` `reconcile_words_3way(`; `:420`; `:474`; copy3 loaded `:596-606`; called `:707`.

**S-dict9 — `dictionary-agent_prompts.md:19` (thresholds)**
- Verbatim: "Threshold: ratio > 80 is likely the same word with OCR errors; ratio < 60 is likely a genuine edition difference."
- Problem: the 80/60/60-80 bands are not the thresholds in `reconcile.py`. The dedup helper uses `threshold = 75` and `partial_ratio >= 90`; the copy3 region match uses `ratio < 0.50`. No three-band classifier exists.
- Triage: reconcile documented thresholds with the actual constants, or mark as illustrative-only.
- Code evidence: `reconcile.py:66` `threshold: float = 75`; `:82` `> threshold`; `:85` `>= 90`; `:340` `if ratio < 0.50`.

### Note on `README.md:120` (dictionary auto-download) — also Stale [needs_nuance]
Filed under both Stale and Ambiguity; see Ambiguity §A-dict for the fuller treatment. Verbatim: "All are public domain OCR from Internet Archive, downloaded automatically on first use." Corrected claim: Edgren and Hoare each have a one-time download routine for raw source text, but all three dictionaries' chunked text is committed, and Zingarelli has no download path at all; in normal use nothing is downloaded on first use. Triage: state that the chunked dictionaries are committed (no fetch needed), only the regenerable raw OCR is fetched on demand, and Zingarelli ships chunked with no download path.

---

## 2. Gaps

### High

**G-rev1 — `REVIEW.md:107` (`audit_divergences.py` → `readjudicate.py` handoff)**
- Verbatim: the `audit_divergences.py` table row (Outputs `data/divergence_audit_candidates.json`, `state/audit/report.md`).
- Problem: the documented output path is wrong on both directory and filename; the script writes `state/audit/divergence_candidates.json`. The consumer `readjudicate.py:33` reads `data/divergence_audit_candidates.json` — a different path the writer never produces. On disk both files exist with identical size (282632 bytes), confirming a manual copy/rename is required. That handoff is an undocumented Track-3 operation.
- Triage: correct the output to `state/audit/divergence_candidates.json`, and document (or eliminate) the manual copy/rename to `data/divergence_audit_candidates.json` that `readjudicate.py` requires.
- Code evidence: `audit_divergences.py:22,37,256,288`; `readjudicate.py:33,57`; both files 282632 bytes on disk.
- (Cross-ref Stale §S-rev1: same path defect.)

**G-readme-translate — `README.md:42-54` (regeneration guard)**
- Verbatim: the Usage block `uv run python pipeline.py` / `--step cleanup --llm-cleanup` / `--step translate`.
- Problem: three documented Usage commands are blocked by the regeneration guard and hard-abort (exit 2) for any non-TTY caller. `pipeline.py` gates `--step all`, `--step cleanup`, and `--step translate` via `_require_human_regen_consent`. The README presents them as ordinary runnable commands with no mention of the guard, the consent prompt, or `PER_LA_LIBERTA_ALLOW_REGEN=1`.
- Triage: add a note in Usage that cleanup/translate/all are regeneration-guarded (abort without an interactive TTY or `PER_LA_LIBERTA_ALLOW_REGEN=1`), as already explained in `CLAUDE.md`.
- Code evidence: `pipeline.py:27` `REGEN_STEPS={'cleanup','translate'}`; `:30-71` `_require_human_regen_consent` (exit 2); called at `:177` (all), `:233` (cleanup), `:264` (translate); `:81` `default="all"`. README grep for guard terms = 0 hits.

**G-readme-multimodel — `README.md:42-54` (multi-model invocation absent)** [needs_nuance]
- Verbatim: the `# Individual steps` block (download/reconcile/cleanup/translate/typeset).
- Problem: the README step table (line 22) states the live edition was produced by the multi-witness path, but the Usage section never shows how to invoke it. The bare `--step translate` runs the single-model path, not the published one.
- Corrected claim: `--multi-model` is not entirely undocumented — it appears in the step table (line 22) and prose (line 11). What is absent is any runnable Usage example: the Usage section shows only the bare single-model `--step translate`, and the companion flags `--draft-models` / `--synth-model` appear nowhere in the README. A reader following only Usage cannot reproduce the published multi-witness edition.
- Triage: add a multi-model translation example to Usage (`--step translate --multi-model`) and document `--draft-models` / `--synth-model`, noting it produced the live edition.
- Code evidence: `pipeline.py:136-147`; `:262-289` (multi_translate vs single-model branch); README grep: `--draft-models`/`--synth-model` 0 hits.

**G-readme-deploy — `README.md:101-110` (typeset auto-syncs docs/)**
- Verbatim: the deploy block (same as Stale §S11).
- Problem: `typeset.py` auto-syncs the edition into `docs/` on every run (with path rewrites) and the README never documents this. The manual `cp output/bilingual.html docs/index.html` would clobber typeset's path-corrected `docs/index.html`.
- Triage: document that `--step typeset` auto-syncs into `docs/` (with path rewrites); replace or remove the manual `cp` block, leaving only `git add/commit/push`.
- Code evidence: `typeset.py:1598-1612` (sync comment, path fix-ups, "Synced to docs/").
- (Merged: same defect as Stale §S11 and Ambiguity §A2.)

**G-pipeline-typo — `PIPELINE.md:285-340` (Step 8: typography restoration undocumented)**
- Verbatim: "**Italian paragraphs:** verso column, markdown italics → `<em>`".
- Problem: Step 8 documents only "markdown italics → <em>" and never mentions the scan-verified typography restoration that is a core part of typeset: loading `data/typography.json` via `typography.py`, applying per-paragraph to BOTH languages, rendering small-caps/bold/verse sentinels, and logging unmatched fragments. A reader would not know typeset restores OCR-flattened type at all.
- Triage: add a substep to Step 8 describing the typography sidecar (load `data/typography.json`, apply per parsed paragraph it+en, render italic/bold/small-caps/verse, log unmatched fragments).
- Code evidence: `typeset.py:708-711` (load_typography); `:955`/`:983` (`apply_typography` it/en); `:294-315` (sentinel→HTML); `:1545-1550` (logs unmatched).

### Medium

**G-claude-typeset-qr — `CLAUDE.md:63 / 207-215` (`--local` / `--site-base`)**
- Verbatim: `uv run python pipeline.py --step typeset`.
- Problem: the Typesetting section describes the QR feature but never documents `--local` (point QR at localhost:8000) or `--site-base` (arbitrary base URL).
- Triage: document `--local` and `--site-base` under `--step typeset`, noting they only affect QR-code target URLs.
- Code evidence: `pipeline.py:152-159`; `:317`; `typeset.py:891-892,1568`.

**G-claude-draftsynth — `CLAUDE.md:36-74` (`--draft-models` / `--synth-model`)**
- Verbatim: `uv run python pipeline.py --step translate --multi-model            # multi-witness synthesis (multi_translate.py)`.
- Problem: the two flags that control the multi-witness path — `--draft-models` and `--synth-model` — are implemented and wired but appear nowhere in `CLAUDE.md`; a reader cannot discover how to add the GPT draft or switch synthesis to Sonnet.
- Triage: add `--draft-models claude,gemini,gpt` and `--synth-model opus|sonnet` to the Running section, noting defaults (claude,gemini / opus).
- Code evidence: `pipeline.py:140-147`; `:262-283`. CLAUDE.md grep: 0 hits.

**G-claude-serve — `CLAUDE.md:36-74 and 261-267` (serve.py)** [needs_nuance]
- Verbatim: `docs/                             # GitHub Pages site (served from /docs on main)`.
- Problem: `CLAUDE.md` does not mention `serve.py`, the local-preview server.
- Corrected claim: `serve.py` is NOT undocumented project-wide — `README.md:86-99` documents launching it (`uv run serve.py`, "open http://localhost:8000"). The accurate gap is that `CLAUDE.md` alone omits a convenience launcher README already covers. (The finding's claim that the doc references localhost:8000 via a `--local` typeset flag is incorrect — no such flag exists in `typeset.py`.)
- Triage: add a one-line note in CLAUDE.md Running (`uv run python serve.py  # preview docs/ at http://localhost:8000, override with PORT`).
- Code evidence: `serve.py:9-21`; `README.md:86-99`.

**G-claude-chapter — `CLAUDE.md:57-62 and 188-191` (`--chapter` scope)**
- Verbatim: `uv run python pipeline.py --step refine --chapter p1_capitolo_primo  # refine specific chapters`.
- Problem: undocumented that `--chapter` also scopes the `--multi-model` translate path (honored), and — more importantly — that `--chapter` is silently ignored by the single-model translate path. `--step translate --chapter X` (no `--multi-model`) yields a full-book run.
- Triage: document that `--chapter` filters the `--multi-model` translate path, and that the single-model translate path does not honor it.
- Code evidence: `pipeline.py:282` (chapter_filter=ch_list); `pipeline.py:288-293` (translate() without ch_list); `translate.py:139-143,155` (no chapter param); `multi_translate.py:764,788-790`.

**G-readme-openai-env — `README.md:35-40` (OPENAI_API_KEY)** [needs_nuance]
- Verbatim: the `.env` block (`ANTHROPIC_API_KEY`, `GEMINI_API_KEY`).
- Problem: the build pipeline also accepts `OPENAI_API_KEY` for the multi-model path.
- Corrected claim: `OPENAI_API_KEY` is for the OPTIONAL GPT draft member, enabled only when `gpt` is added to `--draft-models` (default is claude,gemini). It is NOT required for the default build and was NOT used to produce the live edition (`state/multi_drafts/` contains only claude+gemini drafts/evals). Frame as an optional/conditional key, not a key needed because the multi-model path produced the live edition.
- Triage: note `OPENAI_API_KEY` in Setup as optional (only for the gpt draft model in `--multi-model`).
- Code evidence: `pipeline.py:148-151`; `:276`; `providers.py:257-259`; `state/multi_drafts/` sampled chapters.

**G-readme-ocrpdf — `README.md:13-25` (OCR needs local PDF)**
- Verbatim: `| 2. OCR | `ocr.py` | Gemini Flash (page mapping) + Gemini Pro (quality witness) on the LOC PDF scan |`.
- Problem: OCR requires a local PDF that step 1 does not download and the README never mentions. `ocr.py` hardcodes `DEFAULT_PDF` at the repo root; `download.py` fetches only djvu text. If the PDF is absent, OCR is silently skipped with a warning.
- Triage: document that OCR needs the 82MB LOC PDF placed at the repo root (gitignored, not auto-downloaded), and that OCR is silently skipped if missing.
- Code evidence: `ocr.py:17`; `download.py:6-28`; `pipeline.py:192-194`.

**G-readme-harvard-pdf — `REVIEW.md:16,33; CLAUDE.md:218-260` (Harvard PDF prerequisite)**
- Verbatim: "Copy B is the Harvard/Google copy (rendered on demand from PDF)."
- Problem: the review-phase vision-escalation path hard-depends on a gitignored `harvard_perlalibertdall00cresgoog.pdf` at the repo root. No doc names the file, says it must be placed manually, or where to get it. There is no auto-download routine (unlike `edgren.py`/`hoare.py`). A fresh checkout cannot run `build_concordance.py` / second-copy escalation.
- Triage: document the required `harvard_perlalibertdall00cresgoog.pdf` (source archive.org item, exact filename, repo-root location) in REVIEW.md and/or CLAUDE.md File Structure as a manual prerequisite.
- Code evidence: `build_concordance.py:37,52`; `vision_review.py:41,64-74`; `.gitignore:16` (`*.pdf`); no `download_*()` for it.
- Portability tag: BOOK-DATA.

**G-pipeline-italianonly — `PIPELINE.md:285-340` (Italian-only fallback)**
- Verbatim (code, not doc): `has_english = english_path.exists()`.
- Problem: Step 8 does not document that a missing `output/english_translation.md` does not error — typeset emits a warning and generates an Italian-only edition (passing the Italian markdown in place of English).
- Triage: add a note to Step 8 that a missing `english_translation.md` produces an Italian-only edition with a warning.
- Code evidence: `typeset.py:1574-1591` (only italian_path is a hard error; english is soft fallback).

**G-pipeline-flagsremaining — `PIPELINE.md:168` (Step 5 Outputs)**
- Verbatim: "**Outputs:** `output/italian_clean.md`, `data/review_flags.json`, `data/corrections.json`, `state/llm_cleaned/*.txt`".
- Problem: omits `data/review_flags_remaining.json`, produced by `reconcile_flags()` when run with `--llm-cleanup`. By the list's own convention (it includes `state/llm_cleaned/*.txt`, equally conditional) this file belongs there.
- Triage: add `data/review_flags_remaining.json` to Step 5 outputs and a substep noting `reconcile_flags()` runs after cleanup under `--llm-cleanup`.
- Code evidence: `pipeline.py:237-241`; `cleanup.py:1459-1492`.

**G-pipeline-companion — `PIPELINE.md:353,360` (Step 9 mirroring + CSS sync)**
- Verbatim: "4. Mirror `output/companion/images/` → `docs/companion/images/`".
- Problem: two gaps — (1) `build()` mirrors ALL non-markdown assets preserving the tree, not just images; (2) `build()` also syncs `docs/static/bilingual.css` (with a font-path rewrite), neither described as a step nor in the Step 9 Outputs.
- Triage: change the mirror substep to "mirror every non-markdown asset (images, etc.) preserving the tree", add a substep for the `docs/static/bilingual.css` sync, and add it to Step 9 Outputs.
- Code evidence: `companion.py:1081-1088` (rglob non-`.md`); `:999-1007` (CSS write with `../docs/assets/` → `../assets/`).

**G-pipeline-3copies — `PIPELINE.md:54` (Load all three)** — see Ambiguity §A-3copies (filed as ambiguity). Cross-referenced.

**G-rev-readjudicate-flags — `REVIEW.md:108` (`--ids` / `--workers`)**
- Verbatim: the `readjudicate.py` invocation row.
- Problem: omits `--ids` (a fourth scope selector co-equal with `--chapters`/`--prior`/`--all`) and `--workers` (default 6).
- Triage: add `--ids` to the scope options and mention `--workers`.
- Code evidence: `readjudicate.py:206,210,215-216`.

**G-rev-comprehension — `REVIEW.md:147` (`--plan` / `--workers`)**
- Verbatim: `| `comprehension.py` | `python comprehension.py [--chapters …] [--samples N] [--limit K] [--fresh]` |`.
- Problem: omits `--plan` (a no-API dry-run; material given 11,802 calls) and `--workers`.
- Triage: document `--plan` and `--workers`.
- Code evidence: `comprehension.py:494,496`.

**G-norm-section6 — `1913-italian-ocr-normalization-reference.md:54-58`** — see Low (this is a low-severity gap). Cross-referenced below.

**G-norm-ligatures — `1913-italian-ocr-normalization-reference.md:32-40` (Bodoni i↔r / e↔i omitted)**
- Verbatim: "**Problem:** In period typography, f + i/l combinations were cast as single metal sorts (ligatures) ... `fi` → `fi` (correct), but also → `u`, `n`, `ri`, `th`".
- Problem: the reference omits the single most important OCR-confusion class this repo handles (Bodoni i↔r and e↔i boundary substitutions) while elevating f-ligature misreads. A contributor using this doc as the normalization reference would miss the actual dominant failure mode.
- Triage: add a section documenting the Bodoni/Didone i↔r and e↔i confusion and the line-break boundary-substitution strategy (`cleanup.py:76-160`), the repo's primary OCR-correction mechanism.
- Code evidence: `cleanup.py:71-78` ("dominant pattern"); `:640-644` (f-lig subs match doc §4); `vision_review.py:24`; `sample_estimate.py:76`; `readjudicate.py:41`.

**G-dict-oracle — `dictionary-agent_prompts.md:46` (only Edgren named)**
- Verbatim: "## Prompt 2: Period-Appropriate Translation Validation Using 1901 Dictionary".
- Problem: the doc presents Edgren 1901 as THE single period resource; the repo maintains three (Edgren 1901, Zingarelli 1922, Hoare 1915) as a "≥2 of 3" membership oracle. No mention of Zingarelli, Hoare, or the oracle.
- Triage: add the Zingarelli 1922 and Hoare 1915 resources and the multi-dictionary oracle, or scope the doc as Edgren-only by design.
- Code evidence: `assets/dictionary/` has all three; `hoare.py:6-10` docstring; `CLAUDE.md:184,259`.

**G-dict-fullpipeline — `dictionary-agent_prompts.md:129-135` (3-step "full pipeline")**
- Verbatim: "The full pipeline is: 1. **Reconcile** ... 2. **Translate** ... 3. **Review**".
- Problem: collapses the shipped 11-step pipeline (download → ocr → reconcile → triage → cleanup → adjudicate → validate → translate → refine → typeset → companion). A reader of only this reference would have a drastically incomplete mental model.
- Triage: note this is a conceptual high-level sketch, not the actual pipeline; cross-reference `PIPELINE.md`.
- Code evidence: `pipeline.py:179-324` (11-step dispatch).

**G-readme-python — `README.md:27-40; PIPELINE.md:1-16; pyproject.toml:6`** [needs_nuance]
- Verbatim: `uv sync` / `uv run python -m spacy download it_core_news_lg`.
- Problem: README Setup omits the Python `>=3.13` requirement and still instructs a separate spaCy download.
- Corrected claim: the Python `>=3.13` omission is a real, unflagged install gate (`.python-version` enforces it; a reader on <3.13 gets no warning). The manual spaCy download is arguably intentional, not simply redundant: `pyproject.toml` (lines 10-13) pins `it_core_news_lg` so `uv sync` won't prune the manually-downloaded model — so call it conditional/explanatory rather than a flat no-op.
- Triage: add "requires Python >=3.13" to Setup; note the spaCy Italian model is installed/locked by `uv sync`.
- Code evidence: `pyproject.toml:6,7-26`; `uv.lock:556-560`; `.python-version`; `.venv/.../it_core_news_lg`.

### Low

**G-claude-openai-flag — `CLAUDE.md:94-102`**
- Verbatim: "Keys can also be passed via `--api-key` / `--gemini-api-key` flags, but `.env` is preferred."
- Problem: omits `--openai-api-key` (for the GPT draft). The env var `OPENAI_API_KEY` is documented (line 99) but the flag is not.
- Triage: add `--openai-api-key` to the list of key-passing flags.
- Code evidence: `pipeline.py:148-151`; `:272-276`.

**G-claude-workers — `CLAUDE.md:104`**
- Verbatim: "Translation and cleanup can safely run 20-30+ parallel workers."
- Problem: never documents the `--workers` flag (default 1) that controls this, nor that the default is 1 (parallelism is opt-in).
- Triage: document `--workers N` on the translate examples and note the default is 1.
- Code evidence: `pipeline.py:116-119,278,290`.

**G-ocr-pages — `CLAUDE.md:66-69`**
- Verbatim: `uv run python ocr.py --benchmark 50 51 52  # test specific pages`.
- Problem: omits `--pages START END` (1-indexed contiguous range), distinct from `--benchmark`.
- Triage: add `uv run python ocr.py --model pro --pages 50 80  # OCR only pages 50-80`.
- Code evidence: `ocr.py:305-306,330`.

**G-readme-typeset-typo — `README.md:24`**
- Verbatim: `| 8. Typeset | `typeset.py` | Bilingual HTML with facing pages, source scan overlay, revision marginalia |`.
- Problem: neither the table nor the Typesetting section mentions the typography restoration (`data/typography.json` via `typography.py`).
- Triage: mention restored 1913 typography in the typeset step description.
- Code evidence: `typeset.py:708-711,295-309`.

**G-readme-companion-json — `README.md:25`**
- Verbatim: `| 9. Companion | `companion.py` | Renders the hand-authored Reader's Companion to standalone HTML pages |`.
- Problem: omits two JSON index sidecars: `data/companion_citation_map.json` and `data/companion_entity_index.json`.
- Triage: note the companion step also emits the entity/citation JSON indexes.
- Code evidence: `companion.py:1098-1107`.

**G-readme-revnav — `README.md:80`**
- Verbatim: "- Revision marginalia showing tracked translation changes (toggle with the pencil button, navigate with `m` / `Shift+m`)".
- Problem: omits the parallel `p`/`P` navigation for provenance (page-citation) marginalia.
- Triage: add `p` / `Shift+p` provenance-note navigation to the feature list.
- Code evidence: `typeset.py:1530-1537,1501-1528`.

**G-readme-structure — `README.md:122-146` (missing modules)** [needs_nuance]
- Verbatim: the Project structure block (translate.py / refine.py / edgren.py / typeset.py / companion.py).
- Problem: omits core build scripts referenced elsewhere.
- Corrected claim: the block clearly omits `multi_translate.py` (named at line 22 as the live-edition path, imported by `pipeline.py:267`) and `typography.py` (imported by `typeset.py:710`); it lists single-model `translate.py` and helper `edgren.py` but not their counterparts. It also omits `serve.py` (a dev-server utility invoked at line 96) and `hoare.py` (a review-phase oracle module imported only by `classify_deviations.py`; its dictionary is described at line 118 but the script is never named). `hoare.py`/`serve.py` are not "core build scripts."
- Triage: add `multi_translate.py` and `typography.py` (and optionally `serve.py`/`hoare.py`), or state the list is abbreviated.
- Code evidence: `pipeline.py:267`; `typeset.py:710`; `ls *.py`.
- (Cross-ref Ambiguity §A-structure: same omission, ambiguity framing.)

**G-rev-mt — `REVIEW.md:149`**
- Verbatim: `| `mt.py` | `python mt.py [--breadth N] [--severity …]` |`.
- Problem: omits `--min-score` and `--top`, which select which flags get DeepL translations (and are paid for).
- Triage: add `--min-score F` and `--top K`.
- Code evidence: `mt.py:115,116,100-101`.

**G-rev-boxcrops — `REVIEW.md:72`**
- Verbatim: `| `box_crops.py` | `uv run python box_crops.py [--workers 8] [--refresh]` |`.
- Problem: omits `--limit` (same pattern the doc documents for `classify_deviations.py`).
- Triage: add `[--limit N]`.
- Code evidence: `box_crops.py:102,114`; `REVIEW.md:68`.

**G-rev-contextjudge — `REVIEW.md:93`**
- Verbatim: `| `context_judge.py` | `uv run python context_judge.py [--limit N]` |`.
- Problem: omits `--workers` (default 8), operationally relevant for an LLM-judging step.
- Triage: add `[--workers N]`.
- Code evidence: `context_judge.py:142`.

**G-rev-phantoms — `REVIEW.md:70`**
- Verbatim: the `confirm_phantoms.py` row (Output `patches classified JSON (resolved="phantom")`).
- Problem: also writes a `scan_present` field.
- Triage: note it also writes `scan_present` alongside `resolved="phantom"`.
- Code evidence: `confirm_phantoms.py:90-91`.

**G-rev-concordance — `REVIEW.md:43-54`**
- Verbatim: the five `build_concordance.py --phase` lines.
- Problem: never mentions `--workers`, `--results` (default `~/Downloads/concordance_audit_results.json`, the human-signed audit results read back for the audit→lock handoff), or `--refresh`.
- Triage: document `--results` (and `--workers`/`--refresh`).
- Code evidence: `build_concordance.py:596-598,608`.

**G-rev-deadscript — `REVIEW.md:172-181` (Dead / historical scripts)**
- Verbatim: "## Dead / historical scripts ... Unreferenced by any live code; kept for provenance, **not part of any track**:".
- Problem: `fix_corrupted_passage.py` (a one-off Sonnet-vs-Gemini OCR-correction comparison on the p2_ch18 garbled passage) exists but is documented nowhere, including in this list where it belongs.
- Triage: add `fix_corrupted_passage.py` to the Dead / historical scripts list.
- Code evidence: `fix_corrupted_passage.py:1,154-156`; grep returns no references.

**G-pipeline-css-rewrites — `PIPELINE.md:333-340` (Step 8d docs sync)**
- Verbatim: "- `static/bilingual.css` → `docs/static/bilingual.css`".
- Problem: omits that the CSS copy rewrites font asset paths (`../docs/assets/` → `../assets/`) and that the HTML copy rewrites two relative paths (CSS link and page_images); the doc says only "fix CSS path" for the HTML.
- Triage: note the CSS sync rewrites font paths and the HTML sync rewrites both the stylesheet href and the page_images path.
- Code evidence: `typeset.py:1604-1606,1610-1611`.

**G-pipeline-scoreword — `PIPELINE.md:72` (Step 3b word scoring)**
- Verbatim: "Word scoring: penalizes `*` (-10), brackets (-8), mid-word caps (-4); rewards accents (+5), all-alpha (+2)".
- Problem: omits two penalties: -5 for inner non-letter chars and -3 for a doubled 'ii'.
- Triage: add the two missing penalties.
- Code evidence: `reconcile.py:40-41,48-49`.

**G-pipeline-sitebase — `PIPELINE.md:287` (Step 8 entry)**
- Verbatim: "**Entry:** `typeset(output_dir, state_dir, site_base)`".
- Problem: names `site_base` but never documents how it is supplied or what it controls (`--local`/`--site-base`).
- Triage: note `site_base` is set via `--site-base` (or `--local`, defaulting to localhost:8000) and controls the QR/scan base URL.
- Code evidence: `pipeline.py:152-159,317-318`; `typeset.py:1568`.

**G-pipeline-noise — `PIPELINE.md:178` (Step 5b noise detection)**
- Verbatim: "1. **Noise detection** — skip tokens with <3 alphabetic chars".
- Problem: omits the second noise condition — tokens longer than 3 chars whose alpha/length ratio is below 0.5.
- Triage: add the second branch.
- Code evidence: `adjudicate.py:95-96`.

**G-norm-section6 — `1913-italian-ocr-normalization-reference.md:54-58`**
- Verbatim: "### 6. Additional Period-Specific Watchpoints ... **Circumflex for ii contraction:** ... `studî` ...".
- Problem: the section-6 watchpoints (circumflex ii-contraction, long-s, thin space before punctuation) are presented as concerns for building normalization passes, but none are implemented in this repo's cleanup; the doc does not say so.
- Triage: mark section 6 explicitly as "not yet wired into cleanup.py" (reference-only), or implement detection.
- Code evidence: grep for circumflex/`studî`/thin-space handling over `*.py` finds only deaccent maps; no detection/normalization.

---

## 3. Ambiguity

### High

**A-slug — `CLAUDE.md:214` (the word "slug")** [needs_nuance]
- Verbatim: "Keyed by the **slug** chapter id (`parse_italian_markdown` scheme: `prefazione`, `p2_capitolo_decimottavo`) that `typeset.py` uses — note this differs from the `p1_ch18` scheme `cleanup.py`/`chapter_pages.json` use."
- Problem (as stated): calling the underscore `parse_italian_markdown` scheme "the slug" collides with the function literally named `_slug` (`typeset.py:143`), which produces a different (hyphen) id; three id schemes are in play, presented as two.
- Corrected claim: the word "slug" is an imprecise word choice that collides with a contradictory named entity (`_slug`, whose docstring calls itself "the single source of truth for chapter/part ids"). But the doc is NOT materially misleading about keying `typography.json`: it names the correct function and gives underscore examples that match the actual keys. The fix is to drop/rename "slug" so all three coexisting id forms are named distinctly. (High severity is therefore not well-supported by the "wrong id" harm claim.)
- Triage: stop calling the `parse_italian_markdown` scheme "the slug"; state that `typography.json` is keyed by the underscore `parse_italian_markdown` ids, while `typeset.py` separately derives hyphenated HTML-anchor ids via `_slug`.
- Code evidence: `typeset.py:136-143,719,934,955,983`; `translate.py:44`; `data/typography.json` keys; `data/chapter_pages.json` (`p1_ch18`).

**A-chapter-schemes — `CLAUDE.md:52-62` (`--chapter` two id schemes)**
- Verbatim: `--step cleanup --llm-cleanup --chapter p1_ch18` ... `--step refine --chapter p1_capitolo_primo`.
- Problem: the same `--chapter` flag takes two incompatible id schemes (`p1_ch18` for cleanup; the slug `p1_capitolo_primo` for refine) in the same code block, with no warning. `--step refine --chapter p1_ch18` matches nothing.
- Corrected claim (small precision): refine does not fail entirely silently — `refine.py:293` prints "Italian source not found, skipping" — but it does not error or exit non-zero; it skips and continues.
- Triage: add an inline note that `--chapter` uses the `p1_ch18` scheme for cleanup (chapter_pages.json) but the slug scheme for translate/refine, or cross-reference the line-214 explanation.
- Code evidence: `refine.py:269-303`; `cleanup.py:1229-1230,1331,1403`; `data/reconciled_chapters.json`; `state/translations/` filenames.

### Medium

**A1 — `CLAUDE.md:82` (cache "now empty" vs pipeline.py "31/58")**
- Verbatim: "The local LLM-cleanup cache (`state/llm_cleaned/`) is now empty, so `--step cleanup` would regenerate from scratch".
- Problem: `CLAUDE.md` says "now empty" (true on disk) but `pipeline.py`'s comment/banner assert it "holds only 31 of 58 chapters and ... partly stale." A contributor cannot tell whether 0 or 31 chapters are cached.
- Triage: reconcile the two statements; pick one source of truth.
- Code evidence: `pipeline.py:22-24,43`; `ls state/llm_cleaned/` absent (0 files / dir absent).
- (Merged with Stale §S1; this is the ambiguity facet of the same contradiction.)

**A2 — `README.md:101-110` (which docs/ copy is authoritative)**
- Verbatim: the deploy block.
- Problem: three manual `cp` commands are presented as the post-typeset step, but `typeset.py` already performs all three (and rewrites relative paths the plain `cp` would not). The doc never mentions the auto-sync, so it is unclear which copy is authoritative; following the README breaks the deployed site.
- Triage: state that `--step typeset` already syncs index.html (path-corrected), scan.html, and bilingual.css into `docs/`; reduce the deploy section to `git commit/push`, or warn that a manual `cp` skips the path rewriting.
- Code evidence: `typeset.py:1598-1612`; verified path differences in `output/` vs `docs/`.
- (Merged with Stale §S11 and Gaps §G-readme-deploy.)

**A-gitaddall — `README.md:109`**
- Verbatim: `cd docs && git add -A && git commit -m "Update edition" && git push`.
- Problem: the `cd docs &&` prefix implies the commit is scoped to the docs/ site, but `git add -A` stages every change in the repo (including `output/`, `state/`, in-flight source edits), under an "Update edition" message. (Verified empirically with git 2.50.1; `output/`/`state/` are tracked, not gitignored.)
- Triage: drop `cd docs` and use `git add docs` to stage only the site, or explicitly note `git add -A` commits the whole tree.

**A-serve-docs — `README.md:93-99` (serve.py serves docs/, not output/)** [needs_nuance]
- Verbatim: "For local testing, start the dev server: `uv run serve.py` ... Then open `http://localhost:8000`. QR codes ... will open the scan viewer at `localhost:8000/scan.html#PAGE-PAGE`."
- Problem (as stated): `serve.py` serves `docs/`, not `output/`; a contributor expecting it to serve the just-typeset output, or running it before typeset syncs to docs/, will be confused.
- Corrected claim: the doc never states `serve.py` serves the `docs/` directory, so a reader cannot tell what localhost:8000 renders or that it depends on typeset's auto-sync into docs/. Compounding it, the Deploying section (README.md:105-108) presents docs/ population as a manual `cp` step, contradicting the auto-sync. The documented order (`--step typeset` then serve.py) DOES populate docs/ correctly, so the "freshly typeset edition not visible" risk only materializes on deviation.
- Triage: state that `serve.py` serves the `docs/` directory and that the local preview reflects what `--step typeset` synced into docs/ (not output/).
- Code evidence: `serve.py:10,13,16`; `typeset.py:1598-1612`; `README.md:103,105-108`.

**A-3copies — `PIPELINE.md:54` (Load all three)**
- Verbatim: "1. Load all three raw texts".
- Problem: stated unconditionally, implying all three OCR copies are required. The code makes Copy 3 optional (falls back to 2-way mode). A new contributor would assume a missing Copy 3 is fatal. The doc's own 3b says "If 2 copies" but never reconciles that with this flat "Load all three."
- Triage: reword to "1. Load Copy 1 and Copy 2 (required); load Copy 3 if present (prefer copy3_raw.txt, fall back to copy3_flash.txt) — otherwise run in 2-way mode."
- Code evidence: `reconcile.py:592-608`; `CLAUDE.md:72` (`--skip-ocr`).

**A-chapterpages — `PIPELINE.md:81-83` (chapter_pages.json conditional)** [needs_nuance]
- Verbatim: "3. Build `data/chapter_pages.json` — chapter → PDF page number mapping from Copy 3 page markers ... **Outputs:** `data/reconciled_chapters.json`, `data/flagged_segments.json`, `data/chapter_pages.json`".
- Problem: `chapter_pages.json` is listed as unconditional, but it is only written when Copy 3 is present AND has page markers. In 2-way mode it is never produced.
- Corrected claim: the file is written only inside `if has_copy3 and copy3_page_breaks:` (`reconcile.py:796`; write at 831-834); there is no else branch — in 2-way mode the whole block is skipped. The `chapter_pages = {}` at line 805 is the in-block initialization (runs only when Copy 3 IS present), not an "otherwise" fallback as the finding stated.
- Triage: mark `chapter_pages.json` as a conditional output ("only in 3-way mode, when Copy 3 page markers exist").
- Code evidence: `reconcile.py:796,805,831-834,601-606`; `CLAUDE.md:72`.

**A-concordance-lifecycle — `REVIEW.md:49-51` (which phase writes page_concordance.json)** [needs_nuance]
- Verbatim: the `fit`/`audit`/`lock` `--phase` lines.
- Problem (as stated): the doc assigns ownership of writing `data/page_concordance.json` to `lock` and implies `fit` only computes offsets; in code `fit` writes the file (verified=False) and `lock` re-reads it and flips verified=True — an internal contradiction.
- Corrected claim: the `lock # write verified data/page_concordance.json` line is accurate insofar as `lock` produces the *verified* concordance. The real gap is omission/ambiguity: the doc does not mention that `fit` already writes the file as an unverified draft (verified:False), nor that `audit` and `lock` read that existing file. Not a wrong ownership claim.
- Triage: reword so `fit` is shown to write the draft (verified=false) and `lock` to mark it verified=true.
- Code evidence: `build_concordance.py:11,38,264-272,311,490-528`.

**A-track6-uvrun — `REVIEW.md:147-152` (bare `python` vs `uv run python`)** [needs_nuance]
- Verbatim: `| `comprehension.py` | `python comprehension.py [--chapters …] [--samples N] [--limit K] [--fresh]``.
- Problem (as stated): the Track 6 table uses bare `python …` for all six scripts, but the line-28 rule says scripts must run via `uv run` (google.genai absent from bare python3); a contributor copying the table hits ModuleNotFoundError.
- Corrected claim: comprehension.py's default panel calls Gemini via `from google import genai`, so its copied command fails unless run as `uv run python`. But the genai-specific failure applies ONLY to comprehension.py — `mt.py`/`stage2.py`/`triage_sheet.py`/`poll_comprehension.py` do not import google.genai. The defect is the table-vs-convention inconsistency (the scripts' own headers use `uv run python`), not a contradiction with the line-28 note, which is scoped to `vision_review.py` (a module no Track 6 script imports).
- Triage: make the Track 6 invocation column use `uv run python …` (or note any exceptions).
- Code evidence: `comprehension.py:46,179-180,200`; `mt.py:27,39`; `stage2.py:128,136`; `triage_sheet.py`; `poll_comprehension.py`.

**A-dict-status — `dictionary-agent_prompts.md:1-136` (whole-file status)**
- Verbatim: "# Agent Prompts: Vintage Italian Book Digitization Pipeline ... The full pipeline is: 1. Reconcile the two OCR witnesses ... 2. Translate ... 3. Review".
- Problem: the whole file is an early planning/aspirational spec for a 2-witness design (diff-match-patch, minineedle, collatex, `<ed1>/<ed2>` tags, it_core_news_sm) that does not match the built 3-witness pipeline, yet carries no banner saying so and is linked nowhere from CLAUDE.md's doc map. Mistakable for current architecture guidance.
- Triage: add a top-of-file note marking it a superseded pre-implementation design sketch (kept for provenance), and state the shipped pipeline diverges (3-way, SequenceMatcher/rapidfuzz/symspellpy, it_core_news_lg).
- Code evidence: `reconcile.py:6,246,408,596-599`; `pyproject.toml:13,19,24`; `CLAUDE.md:41,136`; git grep finds zero repo references to the doc and zero `diff_match_patch`/`minineedle`/`collatex`/`it_core_news_sm` in any `.py`.

### Low

**A-11step — `CLAUDE.md:20-34` (11-step vs table numbered 1-9)**
- Verbatim: "**11-step pipeline** (`pipeline.py`): download → ocr → reconcile → triage → cleanup → adjudicate → validate → translate → refine → typeset → companion".
- Problem: the prose says 11 steps (matching `STEPS` minus `all`), but the table numbers only 1-9 with `5b. Adjudicate` / `7b. Refine` as sub-steps; adjudicate/refine are counted as both first-class steps and sub-steps.
- Triage: number the table 1-11, or change the prose to "9 core steps plus 5b/7b" and explain the sub-step distinction.
- Code evidence: `pipeline.py:17-20` (11 steps + `all`); `CLAUDE.md:22-34`.

**A-dict-membership — `README.md:120` (dictionary "downloaded automatically")**
- Verbatim: "All are public domain OCR from Internet Archive, downloaded automatically on first use."
- Problem: a contributor reads this as a network fetch on first run; in fact the chunk files every lookup reads are committed, and Zingarelli has no auto-download path. "Downloaded automatically on first use" describes only the regenerable raw text for two of three dictionaries. Someone could waste time debugging a "missing download" that never happens.
- Triage: clarify that the chunked dictionary files are committed (no fetch to run cleanup/adjudicate/refine), only the regenerable raw OCR (`edgren.py`/`hoare.py`) is fetched on demand, and Zingarelli ships chunked with no download path.
- Code evidence: `adjudicate.py:19,36`; `edgren.py:70-80`; `hoare.py:74-84`; git ls-files (chunks committed).
- (Cross-ref Stale note on `README.md:120`: same defect.)

**A-structure — `README.md:122-146` (Project structure module map)** [needs_nuance]
- Verbatim: `translate.py             # Claude API translation with resume`.
- Problem (as stated): the block reads as the authoritative module map but omits `multi_translate.py` (line 22) and `hoare.py` (line 118).
- Corrected claim: the block is a curated 14-module core-pipeline overview, not an exhaustive map (it omits ~35 of ~50 modules), so it does not falsely imply unlisted files don't exist. The genuine low-severity issue is internal inconsistency: it lists `edgren.py` but not its co-equal sibling `hoare.py` (line 118), and `translate.py` but not `multi_translate.py` (line 22).
- Triage: list `hoare.py` alongside `edgren.py` and `multi_translate.py` alongside `translate.py` for consistency.
- Code evidence: `ls *.py`; `README.md:22,118`.
- (Cross-ref Gaps §G-readme-structure.)

**A-blindfullbook-pages — `REVIEW.md:66`**
- Verbatim: `uv run python blind_fullbook.py [--pages N M] [--workers 8] [--refresh]`.
- Problem: `[--pages N M]` reads as a (start,end) range, but `--pages` is `nargs="*"` — a list of specific page numbers. `--pages 50 80` yields only pages 50 and 80.
- Triage: clarify `--pages` takes a list of specific page numbers (default: all body pages), e.g. `[--pages N [N ...]]`.
- Code evidence: `blind_fullbook.py:115,124,127`.

**A-thinking-default — `REVIEW.md:67`** [needs_nuance]
- Verbatim: `uv run python scan_adjudicate.py --source blind [--chapter ID] [--workers 5] [--thinking low]`.
- Problem (as stated): `[--thinking low]` is bracketed without stating it is non-default; the code default is `medium`, so omitting the flag silently yields `medium`, not the recommended `low`.
- Corrected claim: the same line shows `[--workers 5]`, which matches the actual default (5) — establishing a convention that bracketed values reflect defaults. So `[--thinking low]` misleads (default is `medium`). The decisive evidence is this internal inconsistency.
- Triage: drop the value from the bracket or annotate that `low` is recommended but not the default (default is `medium`).
- Code evidence: `scan_adjudicate.py:164,167`; `blind_fullbook.py:83`; `REVIEW.md:40,66`.

**A-accent-search — `1913-italian-ocr-normalization-reference.md:11`** [needs_nuance]
- Verbatim: "**What to normalize:** For lemmatization and search, treat grave and acute variants of the same word as identical."
- Problem (as stated): framed around "lemmatization and search," a use case this project does not have; a contributor could look for a search-normalization path that does not exist.
- Corrected claim: a minor framing mismatch, not a misleading ambiguity — mitigated by the file's line-3 self-identification as portable reference guidance for the related Athanor pipeline and by line 11's own second sentence ("preserve the source form for display text"), the rule the project actually follows (`cleanup.py:280-282,404`). The only "lemmatize" functions are pre-dictionary-lookup in `edgren.py`/`hoare.py`.
- Triage: reframe to the actual use: accent-insensitive dictionary membership during cleanup, and preserve grave forms in display text.
- Code evidence: `cleanup.py:100-111,275-282,395-414`; `reconcile.py:209-229`; `edgren.py:61`; `hoare.py:66`.

---

## 4. Tone

### Medium

**T-comprehension-calibrated — `REVIEW.md:156`**
- Verbatim: "**Status:** Stage 1 complete and calibrated (1,967 passages, 11,802 calls, 5,661 ranked flag clusters)."
- Problem: "calibrated" implies a validated calibration result (a measured TP/precision figure) but is asserted with only volume counts as support; counts of passages/calls/clusters do not demonstrate calibration. The calibration figure lives in project memory, not cited here.
- Triage: cite the calibration metric inline (e.g. the measured TP rate on the validated tier) or drop "calibrated" and say "complete; calibration recorded in <artifact>."
- Code evidence: `state/comprehension/run_meta.json` (counts match); no quoted TP/precision figure anywhere in REVIEW.md.

### Low

**T-workers-safely — `CLAUDE.md:104`** [needs_nuance]
- Verbatim: "Translation and cleanup can safely run 20-30+ parallel workers."
- Problem (as stated): "safely" is a robustness reassurance with no backing; the code defaults to a single worker.
- Corrected claim: "safely" and "20-30+" are unbacked operational reassurance — translate.py and multi_translate.py default to single-worker and no code asserts/measures/enforces a safe ceiling (only reactive retry on 429s). Additionally, "cleanup" has no worker-count parameter at all (its LLM correction runs via the Batch API or a synchronous `time.sleep(1)` loop), so the "cleanup can run 20-30+ parallel workers" half maps to no real knob. The figure is an inference from the stated Tier-4 limits.
- Triage: soften to a capacity note tied to the Tier-4 rate limits (e.g., "the Tier-4 limits leave headroom for ~20-30 parallel workers"), drop "safely", or cite an actual run.
- Code evidence: `translate.py:455-456`; `multi_translate.py:760`; `cleanup.py:769-782,1386`.

**T-longs-gemini — `1913-italian-ocr-normalization-reference.md:57`**
- Verbatim: "**Long s (ſ):** Gemini claimed this was gone by 1913, which is correct for Italian — but verify against your specific source."
- Problem: citing "Gemini claimed" as evidence, then asserting "which is correct," is unverified hedging that leaks the doc's drafting process into a reference intended to be authoritative; it mixes an unattributed model assertion with a confidence claim and a verify-yourself caveat. (This is the file's sole provenance leak.)
- Triage: replace with a sourced statement (or simply "Long s was not used in Italian by 1913; verify your source if anomalies appear") and drop the model attribution.

**T-verified-concerns — `1913-italian-ocr-normalization-reference.md:3`** [needs_nuance]
- Verbatim: "Context: These are verified concerns for OCR cleanup of early 20th-century Italian printed books."
- Problem (as stated): "verified concerns" implies the items are confirmed and acted upon, but the list mixes implemented behavior, unimplemented watchpoints, and at least one item the code contradicts.
- Corrected claim: "verified concerns" is a slightly loose blanket label — the list mixes well-substantiated period phenomena with items the doc itself flags as needing source-specific verification. It is a general/Athanor-facing reference (line 3 names "the Athanor pipeline"), not a claim about Per la Libertà's implementation, so cleanup.py's deliberate guillemet-stripping is a documented divergence from general advice, not a refutation of a "verified concern."
- Triage: soften to "candidate concerns" or annotate each item with its implementation status against `cleanup.py`.
- Code evidence: `cleanup.py:321-322`; grep over `*.py` for the watchpoints = no matches.

---

## 5. Portability / Book-Specific

Grouped by `portability_tag`, since the pipeline will be reused for other works. Each item flags where the docs present book-specific code as generic, or where a generalizable mechanism carries hardcoded constants.

### BOOK-DATA

These are this work's identifiers/data and do not generalize.

**P-ia-ids — `README.md:150-151` (source-scan IA identifiers)** [needs_nuance]
- Verbatim: the LOC and Google/Harvard `archive.org/details/...` links.
- Problem (as stated): book-specific source-scan identifiers; also a possible mismatch with `download.py:7` (`perlalibertdall00cresgoog`) vs README's `perlalibertdal00cresuoft`.
- Corrected claim: the headline issue is NOT portability — a "## Source" provenance section is meant to name this work's identifiers, and the LOC id (`README.md:150`) matches `download.py:6` correctly. The real, under-weighted issue is a factual doc/code mismatch: `README.md:151` cites the wrong IA item for the Google/Harvard scan (a uoft/Toronto item) while the pipeline fetches `perlalibertdall00cresgoog`. (This is captured authoritatively as Stale §S13.)
- Triage: fix `README.md:151` to `perlalibertdall00cresgoog`; keep the IA links tagged as book-specific data.
- Code evidence: `download.py:6-7`; cross-doc labels at `README.md:15`, `CLAUDE.md:24/111`, `PIPELINE.md:14`.

*(Also tagged BOOK-DATA in their primary dimensions: the `state/llm_cleaned/` `pipeline.py:23,43` finding (Stale §S1); the Harvard PDF prerequisite (Gaps §G-readme-harvard-pdf); the corrected `README.md:151` wrong-id finding (Stale §S13).)*

### BOOK-LOGIC

Generalizable mechanism shape, but the prompt text / rules / keywords are coupled to this book or to Italian.

**P-multiwitness-rubric — `CLAUDE.md:191` (six-dimension synthesis rubric)** [needs_nuance]
- Verbatim: "score each draft on six literary dimensions, then synthesize a final translation with Claude Opus".
- Problem: the six dimensions and synthesis prompts are tuned to this book. `multi_translate.py:41` references "Crespi's conversational narrative voice"; `:49` "Risorgimento-era political terms"; `:88-90` and the synthesis prompt hardcode the title, author, subject, and terminology conventions.
- Corrected claim: the doc does not advertise the method as generalizable, but its neutral phrasing ("six literary dimensions") hides that the scoring rubric is book-coupled rather than a content-agnostic harness.
- Triage: note the multi-witness evaluation rubric and synthesis brief embed Crespi/Risorgimento/di Rudio specifics; the "six dimensions" framing is reusable but the prompt text is not.
- Code evidence: `multi_translate.py:35-90,153-176`.

**P-dehyphenate — `PIPELINE.md:133-137` (Bodoni i→r / i→e substitutions)** [needs_nuance]
- Verbatim: "8. **Dehyphenate** — 4-pass strategy ... OCR boundary substitution (`i→r`, `i→e`) + dictionary check".
- Problem: the `i→r`/`i→e` substitutions are specific to the Bodoni/Didone typeface of this 1913 printing and depend on the Italian dictionary; not portable to a differently-typeset work.
- Corrected claim: this is an inherent, openly-documented design property of a single-book pipeline, not an error/omission in PIPELINE.md, which describes the code correctly. A valid low-severity observation, not a documentation defect.
- Triage: annotate the boundary-substitution pass as typeface/language-specific (Bodoni i/r, i/e; Italian dictionary).
- Code evidence: `cleanup.py:76-78,131-147`; `CLAUDE.md:148`.

**P-accento — `PIPELINE.md:142` (accento facoltativo skip)** [needs_nuance]
- Verbatim: "- Skip accent-only changes (1913 accento facoltativo)".
- Problem: justified by 1913 Italian orthography; only makes sense for Italian source text of this period.
- Corrected claim: the line correctly describes correct, intentionally Italian-specific code; not a documentation error. The only valid observation is a low-severity portability note that, like the whole Italian-bound pipeline, it encodes an Italian-source assumption.
- Triage: mark as an Italian-orthography assumption tied to the 1913 source; flag that the accent-skip heuristic must be revisited for other languages.
- Code evidence: `cleanup.py:280-282,404-405`.

**P-titles — `PIPELINE.md:236` (Italian→English title transform)** [needs_nuance]
- Verbatim: '2. Translate Italian chapter titles to English ("Capitolo Primo" → "Chapter One", etc.)'.
- Problem: hard-coded for Italian ordinals and the literal words "Capitolo"/"Prefazione"; assumes source Italian / target English.
- Corrected claim: a code-portability limitation of a single-book pipeline, NOT a documentation inaccuracy — `PIPELINE.md:236` explicitly says "Translate Italian chapter titles to English" with an Italian example, correctly and self-limitingly describing the behavior. Low severity as a doc finding.
- Triage: note that chapter-title translation is hard-coded Italian→English (Capitolo/ordinals/Prefazione) in `translate.py` and is not language-agnostic.
- Code evidence: `translate.py:297-361,400`.

**P-structure-keywords — `PIPELINE.md:54-58` (boilerplate / chapter / part splitting)**
- Verbatim: "2. Strip boilerplate (cover pages, title pages) ... 4. Split each copy into chapters by heading detection".
- Problem: documented as generic heading detection, but the implementation keys on Italian structural markers specific to this book: PREFAZIONE, INDICE, Capitolo, PARTE SECONDA, FINE DELLA PRIMA PARTE. These are language- and edition-specific and would not detect structure in another work.
- Triage: clarify that boilerplate/chapter/part detection relies on Italian structural keywords hard-coded in `utils.py` and is not language-agnostic.
- Code evidence: `utils.py:138-156,205-227,255-266`; `reconcile.py:610-627`.

**P-accent-rule-section1 — `1913-italian-ocr-normalization-reference.md:7-13` (grave/acute final-e)**
- Verbatim: "**Problem:** Pre-mid-20th-century Italian printing did not consistently distinguish grave (è) from acute (é) on word-final e. You will encounter `perchè`, `benchè`, `poichè` where modern standard prescribes `perché`, `benché`, `poiché`".
- Problem: this section is sound, general Italian-period-typography logic (not book-specific data); it is the portable core of the doc, worth distinguishing from the book-specific Bodoni confusion logic the code relies on.
- Triage: retain as a reusable Italian-period-typography rule; explicitly separate it from book-specific (Bodoni-source) handling.
- Code evidence: borne out by `output/italian_clean.md` (perchè=94 vs perché=22) and honored by `cleanup.py:280-282,400-404`.

### GENERALIZABLE-BUT-HARDCODED

Portable mechanism with a transient/tuned constant baked in.

**P-page-offset — `PIPELINE.md:309-312` (PDF_PAGE_OFFSET=6)**
- Verbatim: 'Clickable "Source pp. X–Y" link (opens scan overlay)'.
- Problem: the page-citation rendering silently depends on a hard-coded `PDF_PAGE_OFFSET=6` mapping this scan's PDF page numbers to printed page numbers. The offset is book/scan-specific (driven by this copy's front-matter length) and is not mentioned in the step description.
- Triage: note the `PDF_PAGE_OFFSET=6` scan-to-printed-page constant in `typeset.py` is book-specific and governs the displayed page citations.
- Code evidence: `typeset.py:17,888-890,404,1095` (offset reused).

**P-vision-model — `REVIEW.md:39` (pinned vision model)**
- Verbatim: "**Primary model:** `gemini-3.1-pro-preview` (best vision of the current crop).".
- Problem: names a specific dated model preview as the vision reader — a point-in-time choice, not a property of the book, hardcoded and needing re-evaluation for reuse.
- Triage: the vision-reading pattern is portable but the pinned model id is a transient choice; call it out as such.
- Code evidence: `vision_review.py:44` (PRIMARY constant); `:156/170/192/199` (default args).

**P-cluster-weights — `REVIEW.md:141` (scoring formula)**
- Verbatim: "Flags are clustered and scored (`8·breadth + 2·consistency + 6·severity + 1·confidence`, where breadth = cross-model agreement).".
- Problem: the formula and weights are a tuning choice, hardcoded, and would carry over verbatim to any reuse without re-calibration.
- Triage: the cluster-scoring approach ports, but the weight constants are calibrated and should be flagged as tunables.
- Code evidence: `comprehension.py:371,379`; `triage_sheet.py` (filters on score, no re-weighting).

**P-panel-models — `REVIEW.md:141-143` (panel model ids)** [needs_nuance]
- Verbatim: "Panel: `claude-opus-4-6`, `gemini-3.5-flash`, `gpt-5.4`, 2 samples each.".
- Problem (as stated): the comprehension panel and Stage-2 Proposer/Checker name specific dated model versions, hardcoded, needing re-selection for reuse.
- Corrected claim: REVIEW.md is a review-phase run log documenting a panel that has already executed and whose outputs are committed; the model ids are material provenance for interpreting the panel's agreement/severity scores, not a reusable spec implying re-selection. The doc accurately matches the code, so this is at most a minor freshness caveat, not a documentation accuracy defect.
- Triage: tag the panel-pattern as portable; treat the specific ids as recorded provenance (transient).
- Code evidence: `comprehension.py:46,172/183/193/200`; `stage2.py:127,135`.

*(The PDF disable finding (Stale §S-pdf) also carries a GENERALIZABLE-BUT-HARDCODED tag for its `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` constant.)*
