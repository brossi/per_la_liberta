# Per la Libertà! — Translation Pipeline

## Project Overview

English translation of *"Per la libertà! (Dalle mie conversazioni col conte Carlo di Rudio, complice di Felice Orsini)"* by Cesare Crespi (1913). The book documents conversations with Count Carlo di Rudio about Italian unification, the Risorgimento, and the Orsini conspiracy against Napoleon III. Published by Canessa Printing Co., 708 Montgomery St., San Francisco.

## Repository

Single repo at `brossi/PER_LA_LIBERTA`. GitHub Pages serves from `/docs` on `main` branch.

## Project Phases

The project has two phases:

- **Build** — `pipeline.py` reconciles the OCR, cleans it, translates it, and typesets the bilingual edition. Documented below and step-by-step in `PIPELINE.md`.
- **Review** — a human-in-the-loop QA phase that runs *against the finished edition* to catch residual OCR/cleanup deviations and translation-fidelity problems (deviation review, vision review, intention review), plus the Reader's Companion. Documented in `REVIEW.md`. This phase is ongoing.

## Build Pipeline Architecture

**11-step pipeline** (`pipeline.py`): download → ocr → reconcile → triage → cleanup → adjudicate → validate → translate → refine → typeset → companion

| Step | File | What it does |
|------|------|-------------|
| 1. Download | `download.py` | Fetches 2 DJVU text copies from Internet Archive (LOC + Google/Harvard) |
| 2. OCR | `ocr.py` | Gemini Flash (page mapping) + Gemini Pro (quality witness) on the LOC PDF scan |
| 3. Reconcile | `reconcile.py` | 2-way paragraph alignment (Copies 1 & 2) with Copy 3 as word-level adjudicator |
| 4. Triage | `triage.py` | LLM categorization + resolution of remaining disagreements |
| 5. Cleanup | `cleanup.py` | Noise removal, regex pre-filters, dehyphenation, symspellpy correction, spaCy NER protection, LLM correction |
| 5b. Adjudicate | `adjudicate.py` | Classifies unresolved hyphens via Zingarelli 1922 dictionary: compound / NER / unknown |
| 6. Validate | `validate.py` | 7 checks: structure, word count, quotes, char coverage, ASCII remnants, word quality (NER-aware), content preservation |
| 7. Translate | `translate.py` (default) / `multi_translate.py` (`--multi-model`) | Default: single-model Claude Sonnet 4.6, extended thinking, per-chapter with resume. `--multi-model`: multi-witness synthesis (Sonnet + Gemini drafts → scored evaluation → Opus synthesis). **The live edition was produced by the multi-witness path** (April 2026), then refined. |
| 7b. Refine | `refine.py` | Post-hoc translation refinement with Edgren 1901 dictionary context + version tracking |
| 8. Typeset | `typeset.py` | Bilingual HTML with Loeb-style facing pages, slide-in source scan overlay, revision marginalia |
| 9. Companion | `companion.py` | Renders the hand-authored Reader's Companion (`output/companion/*.md`) to standalone HTML under `docs/companion/` + entity/citation JSON indexes. Runs after typeset so its deep-links can be checked against the fresh `docs/index.html`. |

## Running

```bash
# Install dependencies
uv sync
uv run python -m spacy download it_core_news_lg

# Full pipeline
uv run python pipeline.py

# Individual steps
uv run python pipeline.py --step download
uv run python pipeline.py --step ocr
uv run python pipeline.py --step reconcile
uv run python pipeline.py --step triage
uv run python pipeline.py --step cleanup
uv run python pipeline.py --step cleanup --llm-cleanup              # sync LLM correction (per-chapter)
uv run python pipeline.py --step cleanup --llm-cleanup --batch      # batch API (all chapters, 50% cheaper)
uv run python pipeline.py --step cleanup --llm-cleanup --chapter p1_ch18  # re-run specific chapter
uv run python pipeline.py --step adjudicate
uv run python pipeline.py --step validate
uv run python pipeline.py --step translate                          # single-model (translate.py)
uv run python pipeline.py --step translate --multi-model            # multi-witness synthesis (multi_translate.py)
uv run python pipeline.py --step translate --with-edgren  # with Edgren 1901 dictionary context
uv run python pipeline.py --step refine --chapter p1_capitolo_primo  # refine specific chapters
uv run python pipeline.py --step refine                              # refine all chapters
uv run python pipeline.py --step refine --revert-to 1                # revert to snapshot version
uv run python pipeline.py --step typeset
uv run python pipeline.py --step companion                          # render the Reader's Companion (unguarded)

# OCR with parallel workers (4x speedup for Pro)
uv run python ocr.py --model pro --workers 4
uv run python ocr.py --model flash --workers 8
uv run python ocr.py --benchmark 50 51 52  # test specific pages

# Skip optional steps
uv run python pipeline.py --skip-ocr     # use existing copy3 or fall back to 2-way
uv run python pipeline.py --no-triage    # majority vote only, skip LLM triage
```

### Regeneration guard (cleanup / translate / all)

`--step cleanup`, `--step translate`, and `--step all` overwrite committed,
hand-tuned text. `output/italian_clean.md` carries scan-grounded deviation-review
fixes applied by hand, and `state/translations/` is the multi-witness synthesis
plus later refinements; neither is reproducible from a fresh run. The local
LLM-cleanup cache (`state/llm_cleaned/`) is now empty, so `--step cleanup` would
regenerate from scratch — and the cleanup stage is itself known to corrupt
source-faithful OCR (the pre-cleanup reconciled text is the better witness). So
re-running these **degrades** `output/*.md` and `state/translations/`.
`pipeline.py` blocks them: each prints
a warning and requires a human to type `regenerate <step>` at an interactive
TTY. There is no TTY for agents, CI, or the auto-mode overseer, so they
hard-abort with exit code 2 — and the same three commands are in the `deny`
list of `.claude/settings.local.json`. A human who genuinely intends to
regenerate can set `PER_LA_LIBERTA_ALLOW_REGEN=1`. Typesetting needs only
`--step typeset`, which is unguarded.

## Environment Variables

Set in `.env` (gitignored, loaded automatically by `pipeline.py` via `python-dotenv`):
- `ANTHROPIC_API_KEY` — cleanup LLM pass, triage, translation, and the review-phase Claude readers/judges
- `GEMINI_API_KEY` — OCR (Gemini Flash/Pro) and all review-phase vision reading (`vision_review.py`)
- `OPENAI_API_KEY` — review-phase only: the GPT-5.4 member of the intention-review comprehension panel and the Stage-2 checker
- `DEEPL_API_KEY` — review-phase only: neutral machine-translation reference (`mt.py`) for intention-review triage

Keys can also be passed via `--api-key` / `--gemini-api-key` flags, but `.env` is preferred.

Anthropic API account is Tier 4 (4,000 RPM, 2M input TPM, 400-800K output TPM for Sonnet). Translation and cleanup can safely run 20-30+ parallel workers.

## Key Technical Decisions

### OCR Strategy
Three independent OCR witnesses:
- **Copy 1**: LOC scan → Internet Archive Tesseract (primary witness)
- **Copy 2**: Google/Harvard scan → IA OCR (primary witness, different physical copy)
- **Copy 3**: LOC scan → Gemini Pro vision (word-level adjudicator only — not used for paragraph structure)

Copies 1 & 2 define paragraph structure via 2-way alignment. Copy 3 participates only at word level: for each aligned paragraph pair, the corresponding text is located in Copy 3 via chunk-anchor substring search, then used as a third witness for `reconcile_words_3way()` majority voting.

### LLM Cleanup Architecture

Two modes for LLM OCR correction:

- **Synchronous** (`--llm-cleanup`): one `messages.create()` call per chapter, useful for re-running individual chapters with `--chapter`
- **Batch API** (`--llm-cleanup --batch`): submits all uncached chapters as a single Anthropic Message Batch, 50% cost reduction, results in ~15-60 minutes

**Full-text LLM cache** (`state/llm_cleaned/{chapter_id}.txt`): the authoritative corrected text per chapter. This replaces the earlier corrections.json context-window approach which was fragile — any change to `clean_text()` would invalidate the 40-char context strings, causing corrections to silently fail to apply.

Cache behavior:
- If cache exists for a chapter: loaded directly, skipping `clean_text()` output
- Manual corrections (non-LLM, `source != "llm"` in corrections.json) still apply on top of cached text
- To refresh a chapter: `--llm-cleanup --chapter X` regenerates its cache from current `clean_text()` + LLM
- Batch mode skips chapters that already have cache files
- Cache is gitignored (transient, regenerable)

`corrections.json` is retained as an audit trail and for manual overrides, but is no longer the primary mechanism for applying LLM fixes.

### Italian Linguistic Handling
- **Accent preservation**: symspellpy corrections skip accent-only changes (e.g., pàtria→patria) — defers to LLM which has sentence context. The 1913 text uses accento facoltativo liberally.
- **NER protection**: spaCy `it_core_news_lg` protects proper nouns from false corrections. Exception: ALL-CAPS words (≥4 chars) bypass NER protection since spaCy mis-tags garbled OCR as PROPN/ORG (e.g., "PRESBNTK" tagged as ORG).
- **ALL-CAPS edit distance**: symspellpy uses `max_edit_distance=2` for uppercase words (≥4 chars) vs distance=1 for normal words, since ALL-CAPS text tends to have more OCR damage.
- **Contraction-aware tokenization**: spaCy splits `dell'Italia` → `["dell'", "Italia"]` for independent correction.
- **Dictionary**: ~708K-entry Italian dictionary (`data/dictionaries/it_combined.txt`) from FrequencyWords + Morph-it morphological lexicon.
- **Stray symbol stripping**: `clean_text()` removes OCR noise characters (`■`, `•`, `^`, `|`, `§`, `¶`, `£→E`) that appear mid-prose.
- **Sentence deduplication**: removes duplicate sentence fragments within paragraphs caused by OCR page-boundary merges.
- **LLM preamble stripping**: regex removes "I'll carefully correct...", "Ecco il testo corretto:", and other meta-commentary the LLM sometimes emits before the corrected text.

### Dehyphenation
Multi-pass strategy in `cleanup.py` to fix words broken across OCR line breaks. Runs before symspellpy to prevent false corrections on fragments.

1. **Simple join** — remove hyphen, check dictionary
2. **OCR boundary substitution** — try `i→r` and `i→e` at the 1-2 characters flanking the hyphen point, then check dictionary. These are the dominant Bodoni typeface confusions.
3. **Drop spurious boundary character** — OCR sometimes reads `r` as `ri`, inserting an extra `i`
4. **Drop duplicated character at boundary** — e.g., `sottosta-ati` → `sottostati`

All passes use accent-insensitive dictionary validation (`_in_word_set`). Minimum 2-char fragments to filter noise.

### Validation (Step 6)
Seven assertion checks in `validate.py`:

1. **chapter_count** — verifies 58 chapters (prefazione + 24 P1 + 33 P2)
2. **no_empty_chapters** — flags chapters with < 50 chars of content
3. **quote_balance** — checks guillemets and smart quotes
4. **italian_char_coverage** — flags if > 0.5% non-Italian characters
5. **no_ascii_remnants** — detects page marker artifacts and OCR noise runs
6. **word_quality** — per-word dictionary lookup + pattern-based garble detection (mid-word noise, mid-word capitals, impossible consonant clusters, English words). Uses spaCy NER to filter proper noun false positives. Zero high-severity flags = PASS.
7. **word_count_preservation** — cleaned text ≥ 60% of reconciled word count

### Zingarelli 1922 Reference Dictionary
Chunked OCR text of the *Vocabolario della Lingua Italiana* by Nicola Zingarelli (2nd edition, 1922) — a period-appropriate authority for the 1913 source text. Public domain, sourced from Internet Archive.

- 22 letter chunks in `assets/dictionary/zingarelli_1922/` (A–Z, ~13MB total) + `index.json`
- Used by `adjudicate.py` to classify unresolved hyphens and by `cleanup.py --llm-cleanup` for Zingarelli context in LLM prompts
- Lookup via `adjudicate.zingarelli_lookup(word)` and `adjudicate.zingarelli_context_for_flags(flags)`

### Edgren 1901 Italian-English Dictionary
OCR text of the *Italian and English Dictionary* by Hjalmar Edgren (1901) — provides period-appropriate Italian→English translations.

- 22 letter chunks in `assets/dictionary/edgren_1901/` (A–Z) + `headwords.json` + `index.json`
- Lookup via `edgren.edgren_lookup(word)` — lemmatizes via spaCy, tries exact headword match, flexible text search, then fuzzy fallback
- Used by `translate.py --with-edgren` for prompt enrichment and `refine.py` for post-hoc refinement

### Hoare 1915 Italian Dictionary
OCR text of *An Italian Dictionary* by Alfred Hoare (Cambridge Univ. Press, 1915) — a period authority published two years after the source text, strong on archaic/literary/technical vocabulary. Public domain (Internet Archive: NOT_IN_COPYRIGHT).

- 26 letter chunks in `assets/dictionary/hoare_1915/` (A–Z, Italian→English body binned by headword letter) + `en_index.txt` (the English→Italian back index, kept whole) + `headwords.json` + `index.json`. `raw.txt` is the regenerable download (gitignored, like Zingarelli's).
- Lookup via `hoare.hoare_lookup(word)` / membership via `hoare.hoare_contains(word)` — lemmatizes via spaCy, then flexible accent/hyphen-tolerant search of the letter chunk and the back index. Exact-headword matching is unusable here because Hoare's OCR headwords are hyphen/accent-mangled (`moltiplic-are`), so flexible search is primary.
- Third member of the period-dictionary membership oracle: a word found in ≥2 of {Zingarelli 1922, Edgren 1901, Hoare 1915} is confidently a real period word — used to tell a cleanup *corruption* of a valid 1913 form from a legitimate fix of OCR garble.

### Translation

Two paths share `--step translate`:

- **Single-model** (`translate.py`, the default): Claude Sonnet 4.6, `max_tokens=128000`, extended-thinking budget configurable via `--thinking-budget` (**default 4096**, *not* 32K), `--no-thinking` to disable.
- **Multi-witness synthesis** (`multi_translate.py`, `--multi-model`): per chapter, draft independently with multiple models (Sonnet + Gemini Pro, optionally GPT), score each draft on six literary dimensions, then synthesize a final translation with Claude Opus, logging provenance (`provenance.json`) and a deterministic omission guard (`synthesis_integrity.json`). Drafts/evals/briefs land in `state/multi_drafts/{ch}/`; resume via `state/multi_translate_progress.json`. **This is the path that produced the live `state/translations/` and `output/english_translation.md`** (April 2026), subsequently refined.

Both paths:
- Extract page provenance markers (`<!-- pages:N-M -->`) before translation, reinsert after
- Detect truncation (`stop_reason == "max_tokens"` or output < 30% of input length)
- Accept `--with-edgren` to enrich prompts with Edgren 1901 dictionary context

### Translation Refinement
- Post-hoc review of existing translations against Edgren 1901 dictionary evidence
- Manual-only step (`--step refine`), never runs as part of `--step all`
- Configurable scope: all chapters, specific chapters via `--chapter`
- Claude annotates changes with `<change old="..." reason="...">new text</change>` inline tags
- Full snapshot of `state/translations/` before each refinement pass
- Revert to any prior version via `--revert-to N`
- Changes visualized as marginalia in the bilingual HTML (toggle via ✎ button)

### Typesetting
- **Typeface**: **Spectral** (display — titles, chapter heads) + **Fraunces** (body — running text, both languages), both OFL, self-hosted under `docs/assets/fonts/`. Fraunces ships as a variable file per slope; Spectral as static weights. This replaced the original Bodoni Moda in the Spectral/Fraunces mobile-typography pass — Spectral is screen-tuned and Fraunces is a warm old-style face, a more legible pairing on phones than the high-contrast Didone while staying period-sympathetic.
- **Layout**: Loeb Classical Library-style facing pages (Italian left, English right)
- **Page citations**: Positioned in the right marginalia gutter (same column as revision annotations), aligned with first paragraph of each chapter. Clicking the label opens the source scan overlay. QR code icon reveals a centered viewport dialog for scanning to another device.
- **Source scan overlay**: Slide-in panel from left showing original PDF page images, navigable with arrow keys
- **TOC**: Slide-in chapter index with collapsible Part 1/Part 2 `<details>/<summary>` sections
- **CSS variables**: All colors, borders, shadows, and backgrounds defined in `:root` — no hardcoded hex values outside `:root` and `@media print`
- **Restored typography** (`data/typography.json` + `typography.py`): OCR flattens the 1913 printing's italics, bold, small caps, and set-off verse lines to plain roman. A hand-curated, scan-verified sidecar restores them. It is the **sole source of truth** and is applied at **one** site — `typeset.py`, per parsed paragraph, just before HTML conversion — so `output/*.md` stay clean text (and `validate.py`, which reads `italian_clean.md`, is unaffected). Each entry has a `style` (`italic` | `bold` | `small-caps` | `verse`) and verbatim `it`/`en` fragments; for `verse`, include the quotation marks in the fragment. Because there is no stable per-paragraph id, a word that recurs in a chapter is disambiguated by an optional `<lang>_anchor` (a longer verbatim context containing the fragment — the target is styled only inside the first anchor instance) and/or `occurrences` (`first` default | `all` | 1-based int); the anchor is part of the entry's identity so two same-word entries and bad anchors are reported independently in the `unmatched` count. The 1913 printer's conventions: italic for set-off verse; **bold** for concept-emphasis (e.g. Mazzini's "Popolo"); guillemets `«»`/quotes for foreign/special terms (already in the text — nothing to restore); drop-cap + opening-word small caps at chapter heads (excluded, see below). Capture any other convention encountered (e.g. letter-spaced *spaziato*) rather than dropping it — easier to prune later than to miss. Keyed by the **slug** chapter id (`parse_italian_markdown` scheme: `prefazione`, `p2_capitolo_decimottavo`) that `typeset.py` uses — note this differs from the `p1_ch18` scheme `cleanup.py`/`chapter_pages.json` use. Detection requires **native-resolution crops** of the page scans (the full-page reads downsample and hide weight/slant); page N in `chapter_pages.json` maps directly to `docs/assets/page_images/page_000N.png`. Rendering: `italic`→`<em>`; `bold`→`<strong>` (via `⟦b⟧`); `small-caps`/`verse` via `⟦sc⟧`/`⟦verse⟧` sentinels → `<span class="sc">`/`<span class="verse">` (`.verse` is a centered italic `display:block` span, kept inline so it doesn't shift the paragraph numbering provenance/revision matching relies on). `typeset` logs any sidecar fragment that matched nowhere. Because it is semantic, the same sidecar will drive a future InDesign print export. The chapter-opening drop cap / first-paragraph no-indent / opening-word small caps are separate, already handled by `_wrap_dropcap` + `.versal`/`.incipit`.

## File Structure

```
data/
  copy1_raw.txt, copy2_raw.txt    # IA DJVU text (step 1)
  copy3_raw.txt, copy3_flash.txt  # Gemini OCR text (step 2)
  copy3_*_page_map.json           # Page boundary maps
  reconciled_chapters.json        # Structured chapters (step 3)
  flagged_segments.json           # Word-level disagreements
  chapter_pages.json              # Chapter → PDF page mapping
  dictionaries/it_combined.txt    # Italian frequency dictionary
  review_flags.json               # Tokens needing LLM review (step 5 sidecar)
  review_flags_remaining.json     # Flags remaining after LLM corrections
  corrections.json                # Audit trail: LLM diffs + manual overrides
  adjudication_results.json       # Zingarelli-classified tokens (step 5b)
  validation_report.json          # Validation results (step 6)
  typography.json                 # Scan-verified italics/small-caps/verse, applied at typeset (step 8)
  companion_entity_index.json     # Companion personae/glossary index (step 9, Phase-2 hook)
  companion_citation_map.json     # Companion chapter→anchor/page map (step 9, Phase-2 hook)
  # Review-phase artifacts (blind_deviations*, cleanup_*, sample_estimate, etc.) — see REVIEW.md
output/
  italian_clean.md                # Cleaned Italian markdown (step 5)
  english_translation.md          # English translation (step 7)
  bilingual.html                  # Bilingual web edition (step 8)
  source_pages.json               # Chapter → IA page URLs (step 7)
  companion/                      # Hand-authored Reader's Companion markdown — source of truth (step 9)
state/
  translation_progress.json       # Per-chapter status (single-model translate.py)
  multi_translate_progress.json   # Per-chapter status (multi-witness multi_translate.py)
  translations/                   # Individual chapter .md files (the live English)
  multi_drafts/                   # Per-chapter drafts, evals, synthesis briefs, provenance (step 7 --multi-model)
  translation_revisions/          # Revision tracking (step 7b)
    revision_log.json             # Version history + snapshot references
    changes/                      # Per-version per-chapter change metadata
    snapshots/                    # Full chapter snapshots by timestamp
  llm_cleaned/                    # Full-text LLM cache per chapter (gitignored)
  llm_batch.json                  # Batch API state (gitignored)
  # Review-phase state (comprehension/, deviation_crops/, scan_adjudication/, etc.) — see REVIEW.md
assets/
  dictionary/zingarelli_1922/     # Chunked 1922 Italian dictionary
  dictionary/edgren_1901/         # Chunked 1901 Italian-English dictionary
  dictionary/hoare_1915/          # Chunked 1915 Italian-English dictionary (3rd oracle member)
  page_images_harvard/            # Copy B (Harvard) pages rendered from PDF on demand (gitignored)
docs/                             # GitHub Pages site (served from /docs on main)
  index.html                      # Bilingual web edition (synced from output/)
  scan.html                       # Standalone scan viewer for QR codes
  companion/                      # Reader's Companion HTML pages + assets (step 9)
  static/bilingual.css            # Stylesheet (synced from static/)
  assets/fonts/                   # Spectral + Fraunces, self-hosted (OFL)
  assets/page_images/             # Rendered PDF pages as PNG — Copy A / LOC (gitignored)
static/
  bilingual.css                   # Typesetting stylesheet (canonical copy)
```

## Current Status

**Build phase — complete and deployed:**
- All build steps (1–9) complete and validated; bilingual HTML deployed via GitHub Pages
- LLM cleanup via Batch API: all 58 chapters corrected, full-text cache in `state/llm_cleaned/`
- Validation passes all 7 checks: zero high-severity garble, zero stray symbols, zero LLM instruction leaks
- Live English is the multi-witness synthesis (step 7 `--multi-model`), since refined; Reader's Companion Phase 1 published under `docs/companion/`
- The PDF on disk is the LOC scan: `public-gdcmassbookdig-perlalibertdal00cres-perlalibertdal00cres.pdf` (82MB, gitignored)

**Review phase — ongoing** (see `REVIEW.md` for the full state):
- Deviation review: scan-grounded adjudication of OCR/cleanup deviations, worked down via an exported review sheet and applied directly to `output/italian_clean.md`
- Intention review: Stage 1 (blind comprehension panel) complete; Stage 2 (bilingual proposals) partial
- English-matching of Italian deviation fixes is deferred to one deliberate sweep after the Italian pass completes

## Related Project

Athanor (`~/LLM/Athanor`) is the user's other OCR text processing pipeline (currently for The Kybalion). The 3-way collation, LLM triage, and validation patterns in this project were adapted from Athanor's architecture.
