# Per la Libertà! — Translation Pipeline

## Project Overview

English translation of *"Per la libertà! (Dalle mie conversazioni col conte Carlo di Rudio, complice di Felice Orsini)"* by Cesare Crespi (1913). The book documents conversations with Count Carlo di Rudio about Italian unification, the Risorgimento, and the Orsini conspiracy against Napoleon III. Published by Canessa Printing Co., 708 Montgomery St., San Francisco.

## Pipeline Architecture

**9-step pipeline** (`pipeline.py`): download → ocr → reconcile → triage → cleanup → adjudicate → validate → translate → typeset

| Step | File | What it does |
|------|------|-------------|
| 1. Download | `download.py` | Fetches 2 DJVU text copies from Internet Archive (LOC + Google/Harvard) |
| 2. OCR | `ocr.py` | Gemini Flash (page mapping) + Gemini Pro (quality witness) on the LOC PDF scan |
| 3. Reconcile | `reconcile.py` | 2-way paragraph alignment (Copies 1 & 2) with Copy 3 as word-level adjudicator |
| 4. Triage | `triage.py` | LLM categorization + resolution of remaining disagreements |
| 5. Cleanup | `cleanup.py` | Noise removal, regex pre-filters, dehyphenation, symspellpy correction, spaCy NER protection |
| 5b. Adjudicate | `adjudicate.py` | Classifies unresolved hyphens via Zingarelli 1922 dictionary: compound / NER / unknown |
| 6. Validate | `validate.py` | 6 assertion checks on cleaned output |
| 7. Translate | `translate.py` | Claude Sonnet 4.6 with extended thinking (32K budget), per-chapter with resume |
| 8. Typeset | `typeset.py` | Bilingual HTML/PDF with Loeb-style facing pages, slide-in source scan overlay |

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
uv run python pipeline.py --step cleanup --llm-cleanup  # with LLM correction + Zingarelli context
uv run python pipeline.py --step adjudicate
uv run python pipeline.py --step validate
uv run python pipeline.py --step translate
uv run python pipeline.py --step typeset

# OCR with parallel workers (4x speedup for Pro)
uv run python ocr.py --model pro --workers 4
uv run python ocr.py --model flash --workers 8
uv run python ocr.py --benchmark 50 51 52  # test specific pages

# Skip optional steps
uv run python pipeline.py --skip-ocr     # use existing copy3 or fall back to 2-way
uv run python pipeline.py --no-triage    # majority vote only, skip LLM triage
```

## Environment Variables

Set in `.env` (gitignored, loaded automatically by `pipeline.py` via `python-dotenv`):
- `ANTHROPIC_API_KEY` — for cleanup LLM pass, triage, and translation
- `GEMINI_API_KEY` — for OCR (Gemini Flash/Pro)

Keys can also be passed via `--api-key` / `--gemini-api-key` flags, but `.env` is preferred.

Anthropic API account is Tier 4 (4,000 RPM, 2M input TPM, 400-800K output TPM for Sonnet). Translation and cleanup can safely run 20-30+ parallel workers.

## Key Technical Decisions

### OCR Strategy
Three independent OCR witnesses:
- **Copy 1**: LOC scan → Internet Archive Tesseract (primary witness)
- **Copy 2**: Google/Harvard scan → IA OCR (primary witness, different physical copy)
- **Copy 3**: LOC scan → Gemini Pro vision (word-level adjudicator only — not used for paragraph structure)

Copies 1 & 2 define paragraph structure via 2-way alignment. Copy 3 participates only at word level: for each aligned paragraph pair, the corresponding text is located in Copy 3 via chunk-anchor substring search, then used as a third witness for `reconcile_words_3way()` majority voting.

### Italian Linguistic Handling
- **Accent preservation**: symspellpy edit-distance-1 corrections skip accent-only changes (e.g., pàtria→patria) — defers to LLM which has sentence context. The 1913 text uses accento facoltativo liberally.
- **NER protection**: spaCy `it_core_news_lg` protects proper nouns from false corrections. Only tokens that are BOTH entity-tagged AND capitalized/PROPN are protected.
- **Contraction-aware tokenization**: spaCy splits `dell'Italia` → `["dell'", "Italia"]` for independent correction.
- **Dictionary**: ~708K-entry Italian dictionary (`data/dictionaries/it_combined.txt`) from FrequencyWords + Morph-it morphological lexicon.

### Dehyphenation
Multi-pass strategy in `cleanup.py` to fix words broken across OCR line breaks. Runs before symspellpy to prevent false corrections on fragments.

1. **Simple join** — remove hyphen, check dictionary
2. **OCR boundary substitution** — try `i→r` and `i→e` at the 1-2 characters flanking the hyphen point, then check dictionary. These are the dominant Bodoni typeface confusions: lowercase `r` is a short vertical stroke whose top-right flag is lost at scan edges, reading as `i`; `e` and `i` differ only in the crossbar.
3. **Drop spurious boundary character** — OCR sometimes reads `r` as `ri`, inserting an extra `i` (e.g., `assicuri-azioni` from `assicurazioni`)
4. **Drop duplicated character at boundary** — e.g., `sottosta-ati` → `sottostati`

All passes use accent-insensitive dictionary validation (`_in_word_set`). Minimum 2-char fragments to filter noise. Tokens that fail all passes are written to `data/dehyphenation_flags.json` with reason codes for adjudication.

### Zingarelli 1922 Reference Dictionary
Chunked OCR text of the *Vocabolario della Lingua Italiana* by Nicola Zingarelli (2nd edition, 1922) — a period-appropriate authority for the 1913 source text. Public domain, sourced from Internet Archive (funded by Wikimedia Italia).

- 22 letter chunks in `assets/dictionary/zingarelli_1922/` (A–Z, ~13MB total) + `index.json`
- Used by `adjudicate.py` to classify unresolved hyphens: compound (both parts in dictionary), NER (proper noun), or unknown (needs LLM)
- Used by `cleanup.py --llm-cleanup` to provide the LLM with dictionary context for flagged tokens in each chapter
- Lookup via `adjudicate.zingarelli_lookup(word)` and `adjudicate.zingarelli_context_for_flags(flags)`

### Translation
- Claude Sonnet 4.6 with 128K max_tokens and 32K thinking budget
- Page provenance markers (`<!-- pages:N-M -->`) extracted before translation, reinserted after
- Truncation detection: flags `stop_reason == "max_tokens"` or output < 30% of input length
- Resumable via `state/translation_progress.json`

### Typesetting
- **Typeface**: Bodoni Moda (variable font with optical size axis) — matches 1913 Italian Didone aesthetic
- **Layout**: Loeb Classical Library-style facing pages (Italian left, English right)
- **Source scan overlay**: Slide-in panel from left showing original PDF page images, navigable with arrow keys
- **TOC**: Slide-in chapter index with collapsible Part 1/Part 2 `<details>/<summary>` sections
- **CSS variables**: All colors, borders, shadows, and backgrounds defined in `:root` (16 variables) — no hardcoded hex values outside `:root` and `@media print`
- **PDF**: WeasyPrint (HTML→PDF). Render per-chapter then merge for performance (not yet implemented — currently single-pass).

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
  review_flags.json                # Tokens needing LLM review: unresolved hyphens, stray symbols (step 5 sidecar, pre-LLM)
  review_flags_remaining.json     # Flags still present in output after LLM corrections (post-LLM)
  corrections.json                # Durable corrections: LLM fixes + manual overrides + image-based fixes (persists across re-runs)
  adjudication_results.json       # Zingarelli-classified tokens (step 5b)
  validation_report.json          # Validation results (step 6)
output/
  italian_clean.md                # Cleaned Italian markdown (step 5)
  english_translation.md          # English translation (step 7, not yet generated)
  bilingual.html                  # Bilingual web edition (step 8)
  bilingual.pdf                   # Bilingual print edition (step 8)
  source_pages.json               # Chapter → IA page URLs (generated during step 7)
state/
  translation_progress.json       # Per-chapter translation status
  translations/                   # Individual chapter .md files
assets/
  dictionary/zingarelli_1922/     # Chunked 1922 Italian dictionary (22 letter files + index.json)
  fonts/Bodoni_Moda/              # Variable + static font files (SIL OFL)
  fonts/Bodoni_Moda_SC/           # Small caps variant
  page_images/                    # Rendered PDF pages as PNG (gitignored)
static/
  bilingual.css                   # Typesetting stylesheet
```

## Current Status

- All pipeline steps (1-8) complete
- LLM cleanup (Sonnet 4.6) made ~5,500 durable corrections across all 58 chapters, including targeted passes on p1_ch13, p1_ch18, p1_ch22, p2_ch13, p2_ch18
- Corrections stored in `data/corrections.json` — persists across re-runs, no redundant API calls
- Review flags: 0 remaining — all 13 flags from reconcile fix resolved via direct corrections + LLM cleanup
- Accepted tokens stored in `corrections.json` with `find == replace` and reason `accepted:*`
- Translation (step 7) and typesetting (step 8) complete — bilingual HTML generated
- The PDF on disk is the LOC scan: `public-gdcmassbookdig-perlalibertdal00cres-perlalibertdal00cres.pdf` (82MB, gitignored)

### Reconcile fix: Copy 3 role inversion (resolved)

The original `align_paragraphs_3way()` treated Copy 3 (Gemini OCR) as an equal paragraph-level witness. Gemini produces 5-16x fewer paragraphs than Copies 1/2 (no blank lines at page boundaries), so `SequenceMatcher` couldn't align them, causing content drops, interleaving, and wholesale appending of unmatched mega-paragraphs.

**Fix applied**: `align_paragraphs_3way()` was replaced with:
1. **2-way paragraph alignment** using existing `align_paragraphs()` on Copies 1 & 2 only
2. **Per-paragraph Copy 3 lookup** via `_find_copy3_text()` — chunk-anchor substring search with quality gate (SequenceMatcher ratio >= 0.50)
3. **Copy 3 never contributes paragraphs** — only used as third witness for `reconcile_words_3way()` when a match is found; falls back to 2-way `reconcile_words()` otherwise

Key functions added to `reconcile.py`:
- `_build_norm_map(text)` — accent-stripped normalization with original position tracking
- `_find_copy3_region(para_norm, ch3_norm, search_start)` — chunk-anchor search with monotonic cursor
- `_find_copy3_text(para_text, ch3_norm, ch3_orig, norm_to_orig, search_start)` — top-level lookup with quality gate

Four previously garbled passages (p1_ch12, p1_ch13, p2_ch13, p2_ch28) were resolved by the reconcile fix. Residual OCR noise in p1_ch13, p1_ch18, p1_ch22, p2_ch13, and p2_ch18 was cleaned up via targeted LLM cleanup passes (Sonnet 4.6).

### Pipeline changes made during cleanup
- `pipeline.py` loads `.env` via `python-dotenv` (added as dependency)
- `--chapter` flag: run reconcile/cleanup on specific chapters, comma-separated (e.g. `--chapter p1_ch01,p1_ch02`)
- Reconcile: per-chapter progress logging, incremental saves to `reconciled_chapters.json`
- Reconcile: `_is_near_duplicate()` uses rapidfuzz two-tier matching (individual + concatenated window) instead of difflib
- Cleanup: `join_broken_paragraphs()` joins paragraphs split at OCR page boundaries (lowercase continuation heuristic)
- Cleanup: `is_noise_line()` strengthened with mixed-alphanumeric and special-character-density checks
- Cleanup: auto-fixes OCR asterisks, missing spaces after punctuation
- Cleanup: `llm_fix_flagged_tokens()` for targeted LLM review with optional dual-model verification (Claude + Gemini)
- Cleanup: stale flag filter removes flags whose token no longer exists in cleaned text
- Cleanup: accepted tokens in `corrections.json` (find == replace) suppress flags across re-runs
- Cleanup skips LLM API calls for chapters that already have durable corrections in `corrections.json`
- Flag reconciliation runs automatically after `--llm-cleanup`, writes `review_flags_remaining.json`
- API client timeout increased to 600s (from 300s) for large chapters
- TODO in `cleanup.py`: add Gemini 3 Pro as fallback LLM when Anthropic API is unavailable

## Related Project

Athanor (`~/LLM/Athanor`) is the user's other OCR text processing pipeline (currently for The Kybalion). The 3-way collation, LLM triage, and validation patterns in this project were adapted from Athanor's architecture.
