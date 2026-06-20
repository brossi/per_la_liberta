# Documentation Audit Diff Review

Companion review of `DOC-AUDIT-DIFF.md`, with spot checks against the
current working tree on June 20, 2026.

This is audit-only. I did not edit the documentation under review and did not
run guarded pipeline steps. I verified claims against the repository files and
filesystem state where practical. Where I could not confirm the qualitative
claim, I say so.

## Executive Verdict

`DOC-AUDIT-DIFF.md` is broadly accurate and useful. Its main conclusion is
right: the union of Run 1 and Run 2 is stronger than either source audit alone,
and the highest-priority work should start with factual/runnable mismatches,
not with tone or portability cleanup.

The diff is strongest on these material issues:

- disabled PDF generation being documented as a real output;
- `state/llm_cleaned/` state contradictions;
- README deploy commands clobbering typeset's path-rewritten `docs/` output;
- wrong Google/Harvard Internet Archive identifier;
- undocumented `claude` CLI dependency for multi-model synthesis;
- default reading edition being English-only rather than facing pages;
- `audit_divergences.py` to `readjudicate.py` path mismatch;
- missing `PIPELINE.md` coverage for scan-restored typography;
- missing local source-PDF prerequisites.

The main weakness of the diff is priority calibration. Some portability findings
are true code constraints but not urgent documentation defects unless the docs
claim the pipeline is reusable as-is. A few chapter-ID findings are also weaker
in the current tree because `pipeline.py` now resolves short and long chapter
IDs for the translate/refine path.

## Confirmed High-Value Findings

These should keep their high or material priority.

### PDF Output Is Not Currently Produced

Confirmed. `typeset.py` defines `generate_pdf()`, but the call is commented out
with a `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` note at `typeset.py:1614`.
No `output/bilingual.pdf` exists. `CLAUDE.md` and `README.md` still describe
HTML/PDF generation in places. The diff's recommendation is accurate and should
be acted on early.

### LLM Cleanup Cache State Is Contradictory

Confirmed, with a current-state nuance. `state/llm_cleaned/` is currently absent,
not just empty. A parked stale directory exists at
`state/_llm_cleaned.stale-2026-04-03/` with 31 files. `pipeline.py:22-43` still
says the live cache is "31/58" and partly stale, while `CLAUDE.md:82` says it is
empty and `CLAUDE.md:276` says all 58 chapters are in the cache. The docs and
guard banner need one shared description.

Recommended wording: the full-text LLM cache is transient/gitignored and is not
present at `state/llm_cleaned/` in the current checkout; 31 stale files were
parked under `_llm_cleaned.stale-2026-04-03/`.

### README Deploy Commands Are Actively Wrong

Confirmed. `typeset.py:1598-1612` writes `docs/index.html`, `docs/scan.html`,
and `docs/static/bilingual.css` itself, with HTML and CSS path rewrites. The
README's manual `cp output/bilingual.html docs/index.html` and
`cp static/bilingual.css docs/static/bilingual.css` bypass those rewrites.

This deserves high priority because following the docs can break the deployed
site. The `cd docs && git add -A` concern is also real: `docs/` is not a nested
Git repo, and `git add -A` from there stages repo-wide changes.

### Wrong Google/Harvard IA Identifier

Confirmed. `README.md:151` points to `perlalibertdal00cresuoft`, while
`download.py:7`, `vision_review.py:41`, and `build_concordance.py:37` use
`perlalibertdall00cresgoog`. This is a factual provenance error, not merely a
portability note.

### `claude` CLI Dependency For Multi-Model Synthesis

Confirmed. `multi_translate.py:507-523` shells out to `claude -p` via
`subprocess.run`, and the synthesis default is the CLI model alias `opus`.
`uv sync` and `ANTHROPIC_API_KEY` alone are insufficient. This is material for
reproducing the live translation path.

### Reading Edition Defaults To English-Only

Confirmed. `typeset.py:173` sets `localStorage.getItem('langFocus') || 'en'`,
and `typeset.py:1321` applies the same default. Facing pages are available via
the Both/IT/EN controls, but they are not the default view. The docs' unqualified
"Loeb-style facing pages" language should be revised.

### Divergence Audit Handoff Is Broken/Undocumented

Confirmed. `audit_divergences.py` writes
`state/audit/divergence_candidates.json`; `readjudicate.py:33` reads
`data/divergence_audit_candidates.json`. Both files currently exist at the same
size and compare identical, which supports the prior audit's conclusion that a
manual copy/rename happened outside the documented workflow.

This is one of Run 2's strongest findings and belongs near the top of triage.

### Typography Restoration Gap In `PIPELINE.md`

Confirmed, with doc-scope nuance. `CLAUDE.md` documents typography restoration
in detail, but `PIPELINE.md` Step 8 does not. The implementation loads
`data/typography.json` through `typography.py` at `typeset.py:708-711`, applies
it to Italian and English at `typeset.py:955` and `typeset.py:983`, and renders
sentinels in `_para_to_html`.

Priority should be medium-high for `PIPELINE.md` because Step 8 otherwise misses
a real semantic transformation.

### Local Source PDFs Are Underdocumented

Confirmed. `ocr.py:17` requires the LOC PDF at the repo root and skips OCR if it
is missing. `vision_review.py:41` and `build_concordance.py:37` require the
Harvard/Google PDF at the repo root for review escalation. Both are gitignored.
The README/REVIEW setup docs should name the filenames and IA sources.

## Priority Adjustments

### C24 Chapter-ID Scheme: Downgrade From High

The diff already suspected Medium; in the current tree I would rate it Low to
Medium, depending on scope.

What is still true:

- `cleanup.py` and `reconcile.py` use short IDs like `p1_ch18`;
- translations, refinement, and `data/typography.json` use long IDs like
  `p1_capitolo_primo`;
- the word "slug" in `CLAUDE.md:214` is imprecise because `typeset.py` also has
  a separate `_slug()` helper for hyphenated HTML ids.

What weakens the old finding:

- `pipeline.py:164-174` now resolves short and long IDs through
  `utils.resolve_chapter_ids()` for the paths that receive `ch_list`;
- `--step refine --chapter p1_ch18` through `pipeline.py` should resolve to the
  long form, so the old "matches nothing" harm is no longer generally true.

Remaining doc fix: document the two persisted ID namespaces, and say that
direct script CLIs may be stricter than `pipeline.py`.

### Portability Findings: Useful Backlog, Not First Triage

The diff is right that many constants are book-, scan-, language-, or
typeface-specific: `PDF_PAGE_OFFSET=6`, IA identifiers, Italian heading words,
Italian ordinal maps, the dictionary trio, Bodoni `i/r` and `i/e` confusion
pairs, and the translation prompt's book identity.

But most of these are accurately described as this project's implementation.
They are portability debt, not documentation correctness bugs, unless a doc says
the pipeline is reusable for arbitrary books without reconfiguration. I would
triage them after the runnable/factual issues above.

Recommended treatment: add a "Portability profile" section rather than editing
each item as if it were a defect. Separate:

- book data to move into a manifest;
- language profile data;
- scan/typeface noise profiles;
- prompt text that is intentionally Per la Liberta-specific.

### Tone Findings: Mostly Low Priority

"calibrated" in `REVIEW.md:156` is the one tone finding I would keep at Medium,
because it implies validation evidence not present in the doc. I could confirm
the run counts in `state/comprehension/run_meta.json`, but I could not confirm a
calibration metric in `REVIEW.md`.

Most other tone items are low priority:

- "best vision of the current crop" should be time-boxed or made factual;
- "honestly", "prime offender", "deliberate", and "confidently" are style or
  implication issues, not correctness blockers;
- "fragile" in the LLM-cache section is justified by the surrounding mechanism
  explanation; only "authoritative" needs softening.

### SpaCy Download Step: Run 2 Had The Better Read

Confirmed. `pyproject.toml` pins `it-core-news-lg` by wheel URL and explicitly
comments that this keeps `uv sync` from pruning the manually downloaded model.
The setup docs should explain this relationship, not simply delete the
`spacy download` line as redundant.

### `OPENAI_API_KEY`: More Nuance Than The Diff Gives

The diff correctly notes README's `.env` block omits review-phase keys. However,
`OPENAI_API_KEY` is not review-only in the code: it is also used by the optional
GPT draft provider in the multi-model build path (`pipeline.py:148-151`,
`providers.py:257-260`). The default live drafts on disk are only Claude/Gemini,
so this is optional for the default published path, but `CLAUDE.md:99` calling it
"review-phase only" is incomplete.

Recommended wording: `OPENAI_API_KEY` is required for review-panel GPT and for
optional `--draft-models ... gpt` build drafts.

### `serve.py` Is Mostly A Documentation Clarity Issue

`uv run serve.py` is not clearly broken; the bigger issue is that README does
not state that `serve.py` serves `docs/`, not `output/`, and that it reflects
the path-rewritten files produced by `--step typeset`.

## Blind Spots / Additional Opportunities

These were missing or under-emphasized in `DOC-AUDIT-DIFF.md`.

### `pipeline.py --chapter` Help Is Now Misleading

`pipeline.py:102-105` says `--chapter` runs "reconcile/cleanup" on specific
chapters. In the current dispatcher it also scopes multi-model translate and
refine, but not the single-model `translate.py` path. Run 2 caught the scope
asymmetry, but the parser help itself should be updated because it is what users
see from `--help`.

### ID Resolution Is Not Applied Uniformly

`pipeline.py` resolves chapter IDs into `ch_list`, but then:

- the reconcile block rebuilds a raw short-ID `ch_list`;
- cleanup passes `args.chapter` directly;
- multi-model translate/refine use the resolved list;
- direct `refine.py --chapter` does not use `utils.resolve_chapter_ids()`.

This is not necessarily a bug, but it should be documented as "pipeline accepts
both forms for translate/refine; cleanup/reconcile use short IDs; direct scripts
may require native IDs."

### `providers.py` Still Mentions A Vestigial OpenAI Extra

`pyproject.toml` includes `openai>=2.30.0` as a base dependency, but
`providers.py:232-246` still says the OpenAI provider requires installing the
`multi-translate` extra. One source audit noted the optional-extra angle for
docs, but the code docstring/error message remains stale.

This is code-level documentation drift, not a primary-doc issue.

### README "Individual Steps" Is An Abbreviated List Without Saying So

README lists only download, reconcile, cleanup, translate, and typeset under
"Individual steps." It omits `ocr`, `triage`, `adjudicate`, `validate`, and
`companion`, even though the table presents a full pipeline. The companion gap
was already caught; the broader issue is that the heading reads exhaustive when
the list is selective.

### "Cleanup Can Safely Run 20-30+ Parallel Workers" Needs Correction

Run 2 caught this as a tone issue, but the diff does not surface it in the final
triage. `pipeline.py` has `--workers` for translation, while cleanup's LLM path
is either batch API or a synchronous per-chapter loop. I do not see a cleanup
worker knob. This should be corrected because it is operational, not just tone.

## Recommended Triage Order

1. Fix docs that can cause wrong commands or broken output:
   README deploy block, regeneration guard in README Usage, PDF output claims,
   wrong IA identifier, `audit_divergences.py` handoff.

2. Document missing prerequisites and runtime dependencies:
   LOC PDF, Harvard PDF, `claude` CLI, Python `>=3.13`, optional GPT/OpenAI
   build use, key/flag matrix.

3. Bring main pipeline docs up to implementation:
   typography restoration in `PIPELINE.md`, typeset default English-only view,
   `--local`/`--site-base`, `--draft-models`/`--synth-model`, conditional
   outputs such as Italian-only typeset and `review_flags_remaining.json`.

4. Add status banners to reference docs:
   `dictionary-agent_prompts.md` is a superseded design prompt; the
   normalization reference is inherited/general guidance and not a full
   description of this repo's implementation.

5. Then handle portability and tone:
   useful, but lower urgency than facts, commands, and prerequisites.

## Things I Could Not Fully Confirm

- I did not independently validate whether `gemini-3.1-pro-preview` was or is
  "best vision of the current crop." That needs an external benchmark or a
  time-boxed local rationale. The current wording remains unsupported by the
  repo.
- I could not confirm a documented calibration metric for the Stage 1
  comprehension review, only the run counts. If the metric exists in another
  artifact, `REVIEW.md` should cite it.
- I did not test `uv run serve.py`; I only verified `serve.py` behavior by code
  inspection and README wording.
- I did not run any guarded regeneration commands.

## Bottom Line

I would treat `DOC-AUDIT-DIFF.md` as a reliable triage base after the adjustments
above. Its strongest recommendations are accurate. The main correction is to
avoid spending early effort on broad portability/tone cleanup before fixing the
docs that currently mislead a maintainer into broken commands, missing
prerequisites, or unreproducible build paths.
