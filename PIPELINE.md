# Pipeline Reference: Step-by-Step Execution Flow

Detailed substep documentation for every stage of the Per la Libertà translation pipeline. Generated from source code analysis.

---

## Step 1: Download (`download.py`)

**Entry:** `download_texts(data_dir)`

1. Check if `copy1_raw.txt` exists → skip if cached
2. `requests.get()` LOC scan DJVU text from Internet Archive → write `copy1_raw.txt`
3. Check if `copy2_raw.txt` exists → skip if cached
4. `requests.get()` Google/Harvard scan DJVU text from Internet Archive → write `copy2_raw.txt`

**Outputs:** `data/copy1_raw.txt`, `data/copy2_raw.txt`

---

## Step 2: OCR (`ocr.py`)

**Entry:** `ocr_pdf(pdf_path, output_path, api_key, model)`

Runs twice: once with Gemini Flash (fast page mapping), once with Gemini Pro (quality witness).

### 2a. Per-page OCR

1. Count PDF pages via PyMuPDF
2. Check `data/ocr_{model}_pages/` for completed pages (resume support)
3. For each uncompleted page:
   - Render page to JPEG at 200 DPI via PyMuPDF
   - Send to Gemini API with OCR prompt (preserve accents, Italian only, mark blanks)
   - Retry up to 3 times with exponential backoff (2s, 8s, 16s)
   - Save result to `page_{NNNN}.json`
4. If `--workers > 1`: process pages in parallel via ThreadPoolExecutor

### 2b. Stitching

1. Load all per-page JSON results in order
2. Concatenate with `⟨PAGE:N⟩` markers between pages
3. Build character-offset → page-number map
4. Write stitched text + page map JSON

**Outputs:** `data/copy3_raw.txt` (Pro), `data/copy3_flash.txt` (Flash), `data/copy3_{model}_page_map.json`

---

## Step 3: Reconcile (`reconcile.py`)

**Entry:** `reconcile(data_dir, chapters=None)`

### 3a. Preprocessing

1. Load all three raw texts
2. Strip boilerplate (cover pages, title pages) from each copy
3. Collapse multiple spaces
4. Split each copy into chapters by heading detection
5. Recover merged chapters in Copy 2 if chapter count doesn't match (size anomaly detection)

### 3b. Per-chapter reconciliation

For each chapter (58 total):

1. **Paragraph alignment:** SequenceMatcher aligns paragraphs from Copy 1 and Copy 2
2. **Copy 3 lookup:** For each aligned paragraph pair, find corresponding text in Copy 3 via `_find_copy3_text()`:
   - Normalize text (strip accents, lowercase)
   - Chunk-anchor substring search with monotonic cursor
   - Quality gate: SequenceMatcher ratio ≥ 0.50
3. **Word-level reconciliation:** For each aligned paragraph:
   - If 3 copies available: `reconcile_words_3way()` — majority vote with `score_word()` tiebreaking
   - If 2 copies: `reconcile_words()` — score-based selection
   - Word scoring: penalizes `*` (-10), brackets (-8), mid-word caps (-4); rewards accents (+5), all-alpha (+2)
   - Disagreements within 2 score points → flagged for triage
4. **Near-duplicate filtering:** `_is_near_duplicate()` via rapidfuzz (threshold 75%) removes paragraphs that appear in both copies due to alignment drift
5. **Incremental save** after each chapter (allows resume)

### 3c. Post-processing

1. Write `data/reconciled_chapters.json` — structured JSON: `{id, title, part, text}`
2. Write `data/flagged_segments.json` — word-level disagreements for triage
3. Build `data/chapter_pages.json` — chapter → PDF page number mapping from Copy 3 page markers

**Outputs:** `data/reconciled_chapters.json`, `data/flagged_segments.json`, `data/chapter_pages.json`

---

## Step 4: Triage (`triage.py`)

**Entry:** `triage_items(data_dir, api_key)`

### 4a. LLM classification

1. Load flagged segments from step 3
2. Filter to items needing LLM review (`resolution_method in ("all_differ", "score_heuristic")`)
3. Process in batches of 5:
   - Build prompt with all 3 copy readings + context
   - Claude Sonnet 4.6 classifies each via tool use: `classify_disagreement`
   - Categories: ocr_confusion, ocr_corruption, punctuation_artifact, alignment_drift, missing_text, archaic_spelling, unknown
   - Returns: proposed_reading, confidence (high/medium/low), needs_human flag

### 4b. Resolution

1. **Auto-accept:** high/medium confidence + plausible correction (SequenceMatcher ratio ≥ 0.4)
2. **Flag for human:** low confidence or implausible correction
3. Apply accepted resolutions directly to `reconciled_chapters.json`

**Outputs:** `data/triage_review.json`, `data/triage_resolved.json`, updated `data/reconciled_chapters.json`

---

## Step 5: Cleanup (`cleanup.py`)

**Entry:** `cleanup(data_dir, output_dir, use_llm, api_key, chapter, batch)`

### 5a. Batch API path (if `--batch --llm-cleanup`)

1. Pre-compute `clean_text()` on all 58 chapters
2. Build batch request list (skip chapters with existing LLM cache)
3. Submit via `client.messages.batches.create()` — 50% cost reduction
4. Poll every 30s until complete
5. Save each result to `state/llm_cleaned/{chapter_id}.txt`
6. Fall through to main loop (everything now cached)

### 5b. `clean_text()` substeps (applied to each chapter's raw reconciled text)

1. **Remove noise lines** — page numbers, OCR artifacts, separator patterns, low letter-ratio lines
2. **Strip stray symbols** — `■ • ¶ § | ~ \` @ # % = + < > { } [ ] \` removed; freestanding `^` removed; `£` → `E`
3. **Collapse blank lines** — 3+ newlines → 2
4. **Join broken paragraphs** — if paragraph starts lowercase, join to previous (OCR page boundary artifact)
5. **Deduplicate sentences** — remove duplicate sentence fragments within paragraphs (SequenceMatcher ratio > 0.75)
6. **Apply regex pre-filters** — high-confidence substitutions: `piii`→`più`, `cbe`→`che`, `eolla`→`colla`, etc. (case-preserving)
7. **Normalize punctuation** — spaced quotes → `"`, doubled `;;`/`,,`/`::` → single, guillemets → `"`, `--` → em-dash
8. **Dehyphenate** — 4-pass strategy for words broken across lines:
   - Simple join + dictionary check
   - OCR boundary substitution (`i→r`, `i→e`) + dictionary check
   - Drop spurious boundary character + dictionary check
   - Drop duplicated boundary character + dictionary check
9. **Dictionary correction** — symspellpy lookup on each spaCy token:
   - Normal words: `max_edit_distance=1`
   - ALL-CAPS ≥4 chars: `max_edit_distance=2` (more OCR damage)
   - NER bypass: ALL-CAPS words skip proper-noun protection (spaCy mis-tags garbled OCR as PROPN)
   - Skip accent-only changes (1913 accento facoltativo)
10. **Remove inline page markers** — residual OCR patterns like `165 3E:`, `dEE o 5E`
11. **Fix OCR asterisks** — `*` between word fragments → join; `'*` → `"`
12. **Fix spacing** — remove space before punctuation; add space after punctuation when missing

### 5c. Text source selection (per chapter)

- **If chapter will get LLM pass:** use `clean_text()` output directly (no stale corrections)
- **If LLM cache exists:** load `state/llm_cleaned/{ch_id}.txt`, apply manual corrections only
- **If no cache, no LLM:** apply `corrections.json` entries as fallback

### 5d. LLM correction (synchronous path, if `--llm-cleanup --chapter X`)

1. Build Zingarelli dictionary context for flagged tokens
2. Send cleaned text to Claude Sonnet 4.6 with OCR correction system prompt
3. Strip LLM preamble (catches "I'll carefully correct...", "Ecco il testo corretto:", etc.)
4. Save full corrected text to `state/llm_cleaned/{ch_id}.txt`
5. Extract corrections diff for audit trail in `corrections.json`

### 5e. Output assembly

1. Build markdown: title page + part headers + chapter headers + page provenance markers + cleaned text
2. Write `output/italian_clean.md`
3. Merge new corrections into `data/corrections.json`
4. Write `data/review_flags.json` (unresolved items for adjudication)

**Outputs:** `output/italian_clean.md`, `data/review_flags.json`, `data/corrections.json`, `state/llm_cleaned/*.txt`

---

## Step 5b: Adjudicate (`adjudicate.py`)

**Entry:** `adjudicate(data_dir)`

For each flagged token from step 5:

1. **Noise detection** — skip tokens with <3 alphabetic chars
2. **NER check** — if both hyphen parts are capitalized and not in Zingarelli → classify as proper noun
3. **Compound check** — if both parts found in Zingarelli (≥4 chars each) → classify as valid compound
4. **Correction attempt** — try dehyphenation passes against Zingarelli: simple join, OCR substitutions, boundary char fixes
5. **Partial match** — one part found → classify as unknown with detail
6. **Default** — neither found → classify as unknown

**Output:** `data/adjudication_results.json`

---

## Step 6: Validate (`validate.py`)

**Entry:** `validate(output_dir, data_dir)`

Seven checks on `output/italian_clean.md`:

1. **chapter_count** — expects ≥3 `##` headers + 57 `###` headers
2. **no_empty_chapters** — each chapter section ≥ 50 chars
3. **quote_balance** — `«`/`»` and `"`/`"` counts match
4. **italian_char_coverage** — ≤0.5% non-Italian characters
5. **no_ascii_remnants** — no page marker artifacts or ALLCAPS+digit noise runs
6. **word_quality** — per-word scan across all 58 chapters:
   - Load spaCy NER model, build entity set from full text
   - For each word ≥4 chars: check mid-word noise, mid-word capitals, consonant clusters (4+), English marker words, dictionary membership
   - NER-filtered: skip proper nouns/place names recognized by spaCy
   - High-severity = mid-word noise, mid-word capitals, or English words (garble indicators)
   - Pass condition: zero high-severity flags
7. **word_count_preservation** — cleaned text ≥ 60% of reconciled word count

**Output:** `data/validation_report.json` with per-check results and per-chapter word quality breakdown

---

## Step 7: Translate (`translate.py`)

**Entry:** `translate(output_dir, state_dir, api_key, workers, thinking_budget, no_thinking, with_edgren)`

### 7a. Per-chapter translation

For each chapter not already completed:

1. Extract and strip page provenance markers (`<!-- pages:N-M -->`)
2. **If `--with-edgren`:** extract content words → batch lookup in Edgren 1901 dictionary → format as context block
3. Send to Claude Sonnet 4.6:
   - Extended thinking enabled (default 4096 token budget)
   - System prompt: Loeb-style translation, preserve paragraph structure, italicize untranslatable Italian
   - User message: Italian text + Edgren context (if enabled)
4. Reinsert page markers at top of translated text
5. Save to `state/translations/{chapter_id}.md`
6. **Truncation detection:** flag if `stop_reason == "max_tokens"` or output < 30% of input length
7. Update `state/translation_progress.json`

If `--workers > 1`: translate chapters in parallel via ThreadPoolExecutor.

### 7b. Assembly

1. Load all chapter translations from `state/translations/`
2. Translate Italian chapter titles to English ("Capitolo Primo" → "Chapter One", etc.)
3. Assemble `output/english_translation.md` with markdown headers
4. Build `output/source_pages.json`: chapter → Internet Archive URL mapping

**Outputs:** `output/english_translation.md`, `output/source_pages.json`, `state/translation_progress.json`, `state/translations/*.md`

---

## Step 7b: Refine (`refine.py`)

**Entry:** `refine(output_dir, state_dir, chapters, api_key, thinking_budget)`

Manual-only step (never runs as part of `--step all`).

### 7b-a. Per-chapter refinement

1. **Snapshot** all current translations before changes
2. For each chapter in scope:
   - Load Italian source + current English translation
   - Extract content words → Edgren 1901 batch lookup → format context
   - Send to Claude Sonnet 4.6 with review prompt:
     - Compare translation against Edgren dictionary evidence
     - Output revised text with `<change old="..." reason="...">new text</change>` tags
   - Parse change tags → extract `{old, new, reason}` list
   - Save revised translation to `state/translations/{ch_id}.md`
   - Record changes to `state/translation_revisions/changes/v{N}_{ch_id}.json`

### 7b-b. Revert support

`--revert-to N` restores all translations from snapshot version N:
1. Load revision log, find target snapshot directory
2. Copy all `.md` files from snapshot back to `state/translations/`
3. Log revert as new revision entry
4. Reassemble `english_translation.md`

**Outputs:** Updated `state/translations/*.md`, `output/english_translation.md`, revision log + snapshots + change metadata

---

## Step 8: Typeset (`typeset.py`)

**Entry:** `typeset(output_dir, state_dir, site_base)`

### 8a. Parse and align

1. Parse Italian markdown → list of chapters with `{title, level, page_range, paragraphs}`
2. Parse English markdown similarly
3. Align Italian/English chapter pairs by position
4. Load revision change metadata (for marginalia)
5. Load source pages mapping (for page citations)

### 8b. Generate HTML

1. **Head:** CSS link with version hash, viewport meta
2. **UI overlays:**
   - Page scan overlay (slide-in panel from left)
   - TOC panel (slide-in chapter index)
   - Font size controls (+/-)
   - Marginalia toggle (✎)
3. **Title page:** facing-page layout with title, subtitle, author
4. **For each chapter:**
   - Part separator pages at Part 1/Part 2 transitions
   - Chapter header: bilingual title spread (verso IT / recto EN)
   - **Page citation:** positioned in marginalia gutter of first English paragraph:
     - Clickable "Source pp. X–Y" link (opens scan overlay)
     - QR icon button (opens centered viewport dialog with scannable QR code)
     - QR encodes URL to standalone scan viewer (`scan.html#START-END`)
   - **Italian paragraphs:** verso column, markdown italics → `<em>`
   - **English paragraphs:** recto column, with revision marginalia:
     - For each revision change: wrap changed text in `<span class="revised">`, add `<span class="marginalia">` with old text + reason
     - Link via shared `data-rev` attributes
5. **Colophon:** production metadata, source links, typeface info
6. **JavaScript:**
   - Page overlay: click citation → load page images, arrow key navigation
   - QR popover: click icon → centered modal with QR code, dismiss on outside click/Escape
   - TOC: build from DOM, collapsible parts, scroll-to-chapter
   - Font size: localStorage persistence, min/max bounds
   - Marginalia: vertical alignment with revised text, hover/click linking, M/Shift+M keyboard navigation, toggle visibility with localStorage

### 8c. Scan viewer

Generate `scan.html` — standalone page for QR code targets:
- Parses URL hash (`#127-134`) for page range
- Displays page images with prev/next navigation
- Keyboard (arrow keys) and swipe support
- Links to Internet Archive for each page

### 8d. Docs sync

Copy to `docs/` for GitHub Pages deployment:
- `output/bilingual.html` → `docs/index.html` (fix CSS path)
- `output/scan.html` → `docs/scan.html`
- `static/bilingual.css` → `docs/static/bilingual.css`

**Outputs:** `output/bilingual.html`, `output/scan.html`, `docs/index.html`, `docs/scan.html`, `docs/static/bilingual.css`
