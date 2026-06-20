# Review Phase Reference

The build pipeline (`PIPELINE.md`) produces a finished bilingual edition. The **review phase** is a separate, human-in-the-loop QA effort that runs *against that finished edition* to catch what the pipeline missed:

- **OCR/cleanup deviations** — places where the published Italian diverges from what the 1913 page actually prints (a misread the OCR shared, or a "correction" the cleanup stage wrongly applied to a valid period form).
- **Translation-fidelity problems** — places where the English is fluent but doesn't faithfully render the Italian, or simply can't be understood on a plain read.

Every track here ends at a **human decision**, never an auto-apply. Models read, judge, and propose; the human adjudicates on a sheet; a small, anchored applier writes the confirmed change. Corrections to the Italian are applied **directly** to `output/italian_clean.md` — the cleanup stage is not re-run (it is the very stage under suspicion; see the regeneration guard in `CLAUDE.md`).

> **Scope note.** As of this writing the Italian deviation pass is being worked down; English-matching of those fixes is deferred to a single later pass *after* the Italian pass completes.

---

## Ground terminology

- **Original / Printed** — the 1913 page scan, the ground truth. Copy A is the Library of Congress scan (`docs/assets/page_images/page_NNNN.png`); Copy B is the Harvard/Google copy (rendered on demand from PDF).
- **Derived / Published** — the edition text, `output/italian_clean.md` (Italian) / `output/english_translation.md` (English).
- **Native-resolution rule** — scan crops are sent to the vision model at native pixels (JPEG q90), never downsampled. Full-page reads blur the single-character distinctions the source's high-contrast type makes load-bearing (c/e, i/r, single vs. double consonants).
- **Second-copy escalation** — when an objective transcription is uncertain, the escalation signal is the *independent physical copy* (Copy B), not a second or weaker model. Cross-model panels are reserved for subjective judgment.
- **3-dictionary oracle** — a word found in ≥2 of {Zingarelli 1922, Edgren 1901, Hoare 1915} is treated as a real period word. Used to distinguish a cleanup *corruption* of a valid 1913 form from a legitimate fix of OCR garble.

---

## Shared infrastructure

### `vision_review.py` — the vision-reading layer

Every track that looks at a scan goes through this module (8 callers). It standardizes native-resolution image handling and model selection. **Must run via `uv run`** — `google.genai` is absent from bare `python3`. Requires `GEMINI_API_KEY`.

> **Scan prerequisites.** Copy B (Harvard/Google) is rendered from the gitignored local file `harvard_perlalibertdall00cresgoog.pdf`, which must be placed at the repo root by hand (from [archive.org/details/perlalibertdall00cresgoog](https://archive.org/details/perlalibertdall00cresgoog)) — there is no auto-download.
> Copy A (LOC) pages are tracked site assets under `docs/assets/page_images/`. Without these, `build_concordance.py` and second-copy escalation cannot run.

| Function | Returns | Purpose |
|----------|---------|---------|
| `page_jpeg(pg)` | bytes | Copy A (LOC) page at native resolution, JPEG q90 |
| `harvard_jpeg(scan_pg)` | bytes | Copy B (Harvard PDF) page rendered on demand, cached as PNG |
| `harvard_page(loc_page)` / `harvard_res(...)` / `harvard_window(...)` | int / str / list | LOC↔Harvard lookups via the concordance |
| `read_images(images, system, user, model=PRIMARY, json_out=True, thinking=None)` | str | Vision question over `(label, jpeg_bytes)` tuples |
| `read_pages(pages, system, user, model=PRIMARY, json_out=True)` | str | Same, by LOC page number |
| `read_json(pages, …)` / `read_json_images(images, …, thinking=None)` | (parsed, raw) | As above + tolerant JSON parse |

- **Primary model:** `gemini-3.1-pro-preview` (the configured PRIMARY vision model, selected 2026-06). Any `gemini-*` name routes to the Gemini client; other names route to Claude.
- **`thinking`** (`low` | `medium` | `high`, Gemini only) trades reasoning budget for cost; `low` is right for objective transcription.
- **`json_out=False`** for long plain-text transcriptions (JSON pinning truncates them).

### `build_concordance.py` — LOC ↔ Harvard folio map

Deterministic, multi-phase build of the verified page concordance that vision escalation depends on. Reads every folio on every LOC and Harvard page, fits piecewise-constant offsets, verifies via opening words, and locks after a human audit — no per-call guessing.

```bash
uv run python build_concordance.py --phase folios   # read folio numbers on every page
uv run python build_concordance.py --phase fit      # fit LOC→Harvard offsets; write data/page_concordance.json as a DRAFT (verified=false)
uv run python build_concordance.py --phase audit    # build audit sheet for human sign-off (reads the draft)
uv run python build_concordance.py --phase lock     # re-read the human-signed results and flip the concordance to verified=true
uv run python build_concordance.py --phase viewer   # Harvard flip-viewer
```
Flags: `--results PATH` (the human-signed audit results read back at `lock`; default `~/Downloads/concordance_audit_results.json`), `--workers N`, `--refresh`.

**Output:** `data/page_concordance.json` (written as a draft by `fit`, marked verified by `lock`; consumed by `vision_review.harvard_*`).

---

## Track 1 — Deviation review

**Purpose.** Catch substantive deviations between the published Italian and the 1913 page that *no OCR witness flagged* — because all three witnesses happened to agree with each other yet disagree with the page. A whole-book blind re-read surfaces candidates; each is then scan-adjudicated, classified, presented on a sheet with a boxed crop of the exact word, and applied if confirmed.

**Data flow:** `blind_fullbook` → `scan_adjudicate --source blind` → `classify_deviations` → (`verify_dittography`, `confirm_phantoms`, `re_audit`) → `box_crops` → `build_deviation_sheet` → *human works the sheet* → `apply_decisions` / (`resolve_splits` → `apply_splits`).

| Script | Invocation | Inputs | Outputs | Purpose |
|--------|-----------|--------|---------|---------|
| `blind_fullbook.py` | `uv run python blind_fullbook.py [--pages N M] [--workers 8] [--refresh]` | LOC pages, `chapter_pages.json` | `data/blind_deviations.json`, cache `state/blind_fullbook/` | Whole-book independent blind re-read (Gemini, low thinking, native res); lists only substantive deviations |
| `scan_adjudicate.py` | `uv run python scan_adjudicate.py --source blind [--chapter ID] [--workers 5] [--thinking low]` | `data/blind_deviations.json`, LOC/Harvard scans | `data/blind_deviations_scanned.json`, cache `state/scan_adjudication_blind/` | Re-read the actual page; report whether the page shows the candidate (source), the published word (false alarm), a third reading, or not-found |
| `classify_deviations.py` | `uv run python classify_deviations.py [--limit N] [--workers 8]` | `…_scanned.json`, 3-dict oracle | `data/blind_deviations_classified.json` | Triage into **restore** (modernization/misread), **keep** (source typo the edition fixed), **review** (dittography/uncertain); detects omissions/dittographies structurally |
| `verify_dittography.py` | `uv run python verify_dittography.py [--dry-run]` | classified JSON, `italian_clean.md` | patches classified JSON (`dup_real`, `suggest_flag`) | Real dittographies show adjacent duplication in the derived text; phantoms don't → flag likely-false findings |
| `confirm_phantoms.py` | `uv run python confirm_phantoms.py [--dry-run] [--workers 6]` | classified JSON, page images | patches classified JSON (`resolved="phantom"`, `scan_present`) | Scan-confirm and auto-clear phantom dittographies |
| `re_audit.py` | `uv run python re_audit.py [--dry-run]` | classified JSON | patches classified JSON (`re_audit` field) | Re-audit unreliable keep verdicts with a cross-architecture panel (Claude Opus 4.8 + Gemini 3.1 Pro); a model **split** is flagged for the human |
| `box_crops.py` | `uv run python box_crops.py [--workers 8] [--limit N] [--refresh]` | classified JSON, page images | `state/deviation_crops/*.png` + `manifest.json` | Locate the disputed word and emit a native-res band crop with a red box around it |
| `build_deviation_sheet.py` | `uv run python build_deviation_sheet.py` | classified JSON, crop manifest | `state/deviation_crops/sheet.html` (gitignored) | Interactive browser sheet: boxed crops, suggested action, magnifier, localStorage verdicts, JSON export |
| `resolve_splits.py` | `uv run python resolve_splits.py` | classified JSON, crops | stdout + `data/split_reads.json` | For panel-split items, read the boxed word on the crop (an objective transcription question the panel couldn't settle) |
| `apply_decisions.py` | `uv run python apply_decisions.py [--dry-run]` | classified JSON, `italian_clean.md` | edits `italian_clean.md`; marks `resolved="applied"` | Apply a worked batch of decisions; each edit anchored to unique context and asserted before writing |
| `apply_splits.py` | `uv run python apply_splits.py` | classified JSON, `italian_clean.md` | edits `italian_clean.md`; marks resolved | Apply the confident panel-split closes that `resolve_splits.py` produced |

**Master worklist:** `data/blind_deviations_classified.json`. Items gain a `resolved` field once applied so they drop from the next sheet build.

**The `apply_*.py` scripts are single-batch appliers, not reusable tools.** Each hard-codes the specific `(id, old, new)` edits worked in that round, asserts each anchor is unique in `italian_clean.md`, then writes. They are committed as an audit trail of exactly what was changed, not re-run.

**Status:** in progress. The sheet has been worked down across several batches (≈862 candidates → ≈768 remaining as of mid-June 2026). Two items are deliberately held: a plausible period spelling awaiting an own-eyes crop read, and a ~1,670-char passage that turned out to be duplicated ~19k chars apart (needs placement analysis before removing either copy).

---

## Track 2 — Cleanup-corruption review

**Purpose.** A targeted complement to Track 1: find places where the **cleanup stage specifically** overwrote a valid period word the OCR had right (the symspell dictionary-correction pass is a frequent source of these). Detected by diffing the pre-cleanup reconciled consensus against the final published text.

| Script | Invocation | Inputs | Outputs | Purpose |
|--------|-----------|--------|---------|---------|
| `diff_cleanup.py` | `uv run python diff_cleanup.py [--tier1]` | `reconciled_chapters.json`, `italian_clean.md` | `data/cleanup_corruption_candidates.json` | Isolate 1:1 word substitutions where cleanup changed a word; deterministic |
| `context_judge.py` | `uv run python context_judge.py [--limit N] [--workers N]` | `cleanup_corruption_candidates.json` | `data/cleanup_worklist_judged.json` | Claude Sonnet 4.6 judges pre- vs post-cleanup word pairs in context (a pre-filter, not ground truth) |
| `scan_adjudicate.py` | `uv run python scan_adjudicate.py --source cleanup` | `cleanup_worklist_judged.json`, scans | `data/cleanup_worklist_scanned.json` | Same scan-adjudication engine as Track 1, pointed at the cleanup worklist |
| `build_cleanup_sheet.py` | `uv run python build_cleanup_sheet.py` | `cleanup_worklist_scanned.json`, page images | `state/scan_adjudication/audit.html` (gitignored) | Interactive audit sheet: source vs. final, scan verdict with exact word read, human confirms/overturns |

> `context_judge.py` belongs to **this** track — it is not part of intention review, despite living near it.

---

## Track 3 — Divergence audit (reconciler-based)

A second, deterministic detector for pipeline-introduced errors, independent of the blind read. `audit_divergences.py` finds (A) where reconciliation chose a non-dictionary word over a similar dictionary alternative, and (D) where the published text overrides a Copy 2 + Copy 3 consensus. `readjudicate.py` then re-reads each candidate against the scans.

| Script | Invocation | Inputs | Outputs | Purpose |
|--------|-----------|--------|---------|---------|
| `audit_divergences.py` | `uv run python audit_divergences.py` | `flagged_segments.json`, copy2/copy3 raw, `italian_clean.md` | `state/audit/divergence_candidates.json`, `state/audit/report.md` | Deterministic detectors A & D for pipeline-introduced errors |
| `readjudicate.py` | `uv run python readjudicate.py [--all \| --chapters … \| --ids … \| --prior uncertain,other] [--no-escalate] [--refresh] [--workers N]` | `state/audit/divergence_candidates.json` (the writer's path — read directly, no manual copy), scans, concordance | `data/divergence_audit_verdicts_gemini.json`, cache `state/readjudication/` | Re-adjudicate candidates with Gemini primary; escalate uncertain/contradictory reads to Copy B (same page, independent printing) |

**Status:** `readjudicate.py` produced 496 verdicts (Gemini path); prior Claude verdicts in `data/divergence_audit_verdicts.json` are left untouched for comparison.

---

## Track 4 — Sampling estimate (residual error rate)

The blind read cannot catch the case where *all* OCR witnesses agree with each other **and** with the published text but the page actually prints something else — there is no internal disagreement to flag. `sample_estimate.py` measures that residual rate: blind-read a random sample of pages, align against the published text, scan-adjudicate every divergence, and extrapolate a misread rate with a 95% CI to the whole book.

| Script | Invocation | Inputs | Outputs | Purpose |
|--------|-----------|--------|---------|---------|
| `sample_estimate.py` | `uv run python sample_estimate.py [--pages 40] [--seed N] [--workers 6] [--refresh]` | `italian_clean.md`, `chapter_pages.json`, random LOC pages | `data/sample_estimate.json`, cache `state/sample_estimate/` | Capture–recapture estimate of residual OCR-divergence rate |
| `build_audit_sheet.py` | `uv run python build_audit_sheet.py [--misreads-only]` | `state/sample_estimate/page_*.json`, page images | `state/sample_estimate/audit.html` (gitignored) | Human-audit sheet for the sampled misreads, grouped by page with sticky scan image |

---

## Track 5 — Ellipsis restoration

Crespi's 1913 printing uses multi-dot suspension points (4, 5, 6 dots) expressively; cleanup flattened them all to three. `restore_ellipses.py` matches the long dot-runs from the OCR against the derived text via both-side anchors and restores the true counts.

```bash
uv run python restore_ellipses.py [--dry-run]          # Italian
uv run python restore_ellipses.py --english            # mirror counts into the English
```
**Status:** Italian largely restored (≈167/189); a handful await scan verification, and the English mirror is partial (`data/ellipsis_english_gaps.json` lists the manual-review spots). Idempotent — already-correct sites are skipped.

---

## Track 6 — Intention review (translation fidelity)

**Purpose.** A two-stage translation-QA track that first finds passages a reader can't understand, then proposes evidence-based fixes — both non-destructive, ending at a human triage sheet.

**Stage 1 — blind comprehension** (`comprehension.py`). A 3-model panel reads the English **blind to the Italian** (the Italian is used only for segment keys) and flags passages that can't be confidently understood on one read. Panel: `claude-opus-4-6`, `gemini-3.5-flash`, `gpt-5.4`, 2 samples each. Flags are clustered and scored (`8·breadth + 2·consistency + 6·severity + 1·confidence`, where breadth = cross-model agreement).

**Stage 2 — bilingual proposals** (`stage2.py`). For each flag, a Proposer (Claude Opus 4.6) reads the Italian source + aligned context + neutral DeepL MT + the panel's rationales and drafts `{verdict, draft, rationale}` (verdict ∈ retranslate / gloss / leave / recoverable). An independent Checker (GPT-5.4, different architecture) vets it for faithfulness and verdict agreement, guarding against fluent-but-wrong.

| Script | Invocation | Inputs | Outputs | Purpose |
|--------|-----------|--------|---------|---------|
| `comprehension.py` | `uv run python comprehension.py [--chapters …] [--samples N] [--limit K] [--plan] [--workers N] [--fresh]` | `english_translation.md` | `state/comprehension/flags.jsonl`, `ledger.txt`, `run_meta.json`, `raw/*.txt` | Blind English comprehension panel (Stage 1). `--plan` is a no-API dry-run |
| `poll_comprehension.py` | `uv run python poll_comprehension.py [--interval N] [--once]` | running-job cache | stdout | Standalone progress monitor for a Stage-1 run |
| `mt.py` | `uv run python mt.py [--breadth N] [--severity …] [--min-score F] [--top K]` | Italian text, DeepL | `state/comprehension/mt_cache.json` | Neutral DeepL reference translations (run before the triage sheet); `--min-score`/`--top` select which flags get paid translations |
| `align.py` | imported | EN/IT markdown | paragraph alignment | EN↔IT alignment via Needleman–Wunsch on translation-invariant tokens; supplies the bilingual window |
| `stage2.py` | `uv run python stage2.py [--breadth 3] [--severity high] [--anchors …] [--limit K] [--refresh]` | `flags.jsonl`, both editions, MT cache | `state/comprehension/proposals.jsonl` | Bilingual proposal engine + independent checker (Stage 2) |
| `triage_sheet.py` | `uv run python triage_sheet.py [--breadth N] [--min-score F] [--top K]` | `flags.jsonl`, `proposals.jsonl` | `state/comprehension/triage.html` | Human triage interface (filters, search, verdict radios, localStorage) |

**Models/keys:** `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY` (panel + checker), `DEEPL_API_KEY` (MT).

**Status:** Stage 1 complete (1,967 passages, 11,802 calls, 5,661 ranked flag clusters); the panel's flags were spot-checked at ≈98% true-positive on a breadth-3 / high-severity slice. Stage 2 partial — 712 proposals (157 ready / 374 quick-edit / 181 needs-you). The triage sheet renders both. `mt.py` must be run before `triage_sheet.py` or the MT column shows null.

---

## Reader's Companion (also Build step 9)

`companion.py` is documented as build step 9 in `CLAUDE.md`/`PIPELINE.md`; it is mentioned here because Phase 2 is review-adjacent. Phase 1 (complete) renders the hand-authored `output/companion/*.md` into standalone HTML under `docs/companion/` and emits two machine-readable indexes (`data/companion_entity_index.json`, `data/companion_citation_map.json`). It makes **no model calls** — it is a pure renderer. Phase 2 (pending) would consume those indexes for in-text entity popovers and per-chapter orientation drawers in the reading edition; the indexes are built but the popover rendering is not.

```bash
uv run python pipeline.py --step companion   # render (integrated)
uv run python companion.py                    # render (standalone)
uv run python companion.py --check-links      # probe external links (network, on demand)
```

---

## Dead / historical scripts

Unreferenced by any live code; kept under `archive/one_off_scripts/` for
provenance, **not part of any track**:

- `archive/one_off_scripts/write_ch3_synth.py`, `archive/one_off_scripts/write_ch6_synth.py`, `archive/one_off_scripts/write_ch8_synth.py`, `archive/one_off_scripts/write_ch6_out.py`, `archive/one_off_scripts/write_ch32.py` — empty stubs / placeholders, never executed.
- `archive/one_off_scripts/write_provenance.py` — one-off that hand-wrote one chapter's `provenance.json`.
- `archive/one_off_scripts/write_ch20_synth.py` — one-off that wrote a single chapter's English to a hard-coded Desktop path.
- `archive/one_off_scripts/extract_context.py` — per-chapter narrative-context extraction (run once, cached to `state/context_extractions/`); built for the multi-witness synthesis brief but not currently wired into it.
- `archive/one_off_scripts/fix_corrupted_passage.py` — one-off Sonnet-vs-Gemini OCR-correction comparison on the garbled p2_ch18 passage. Its saved text outputs are archived under `archive/one_off_data/`.

These archived files can stay out of the active root without effect on any
track.
