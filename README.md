# Per la Libertà! — OCR Reconciliation & Translation Pipeline

Translates Cesare Crespi's 1913 Italian book *Per la Libertà!* into English by reconciling two OCR sources from Internet Archive, cleaning artifacts, and translating via Claude API.

## Prerequisites

- Python 3.11+
- `requests` and `anthropic` packages installed
- `.env` file with `ANTHROPIC_API_KEY=sk-ant-...`

## Pipeline Steps

Each step can be run individually or all at once.

### 1. Download OCR texts

```bash
python pipeline.py --step download
```

Fetches both plain-text OCR copies from Internet Archive into `data/`.

### 2. Reconcile two OCR sources

```bash
python pipeline.py --step reconcile
```

Aligns chapters/paragraphs/words from both copies, picks the best reading for each disagreement. Outputs `data/reconciled_chapters.json` and `data/flagged_segments.json`.

### 3. Clean up OCR artifacts

Regex-only (fast, free):

```bash
python pipeline.py --step cleanup
```

With LLM-assisted Italian correction (fixes ~5000 remaining OCR ambiguities). Shows a live progress bar:

```bash
export $(cat .env | xargs)
PYTHONUNBUFFERED=1 python pipeline.py --step cleanup --llm-cleanup
```

Outputs `output/italian_clean.md`.

### 4. Translate to English

```bash
export $(cat .env | xargs)
python pipeline.py --step translate
```

Translates chapter-by-chapter using Claude Sonnet 4.6. Resumable — if interrupted, re-run and it picks up where it left off. Progress tracked in `state/translation_progress.json`.

Outputs `output/english_translation.md`.

### Run everything at once

```bash
export $(cat .env | xargs)
python pipeline.py --step all --llm-cleanup
```

## Project Structure

```
pipeline.py          # CLI orchestrator
download.py          # Fetch OCR texts from Internet Archive
utils.py             # Chapter parsing, normalization, boilerplate stripping
reconcile.py         # Dual-source alignment and word-level reconciliation
cleanup.py           # OCR artifact removal + optional LLM correction
translate.py         # Claude API translation with resumability

data/                # Working files (downloads, intermediate outputs)
output/              # Final Italian + English markdown
state/               # Translation progress and per-chapter files
```
