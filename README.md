# Per la Libertà! / For Freedom!

English translation of *Per la Libertà! (Dalle mie conversazioni col Conte Carlo di Rudio, complice di Felice Orsini)* by Cesare Crespi (1913). The book documents conversations with Count Carlo di Rudio about Italian unification, the Risorgimento, and the Orsini conspiracy against Napoleon III.

Published by Canessa Printing Co., 708 Montgomery St., San Francisco.

**Live edition**: [brossi.github.io/PER_LA_LIBERTA](https://brossi.github.io/PER_LA_LIBERTA/)

## Pipeline

A 10-step pipeline reconciles two independent OCR scans from Internet Archive, cleans artifacts via dictionary validation and LLM correction, translates with Claude Sonnet 4.6, and typesets a bilingual Loeb-style facing-page edition.

| Step | File | What it does |
|------|------|-------------|
| 1. Download | `download.py` | Fetches 2 DJVU text copies from Internet Archive (LOC + Google/Harvard) |
| 2. OCR | `ocr.py` | Gemini Flash (page mapping) + Gemini Pro (quality witness) on the LOC PDF scan |
| 3. Reconcile | `reconcile.py` | 2-way paragraph alignment with Copy 3 as word-level adjudicator |
| 4. Triage | `triage.py` | LLM categorization + resolution of remaining disagreements |
| 5. Cleanup | `cleanup.py` | Noise removal, dehyphenation, symspellpy correction, spaCy NER protection |
| 5b. Adjudicate | `adjudicate.py` | Classifies unresolved hyphens via Zingarelli 1922 dictionary |
| 6. Validate | `validate.py` | 6 assertion checks on cleaned output |
| 7. Translate | `translate.py` | Claude Sonnet 4.6 with extended thinking, per-chapter with resume |
| 7b. Refine | `refine.py` | Post-hoc refinement with Edgren 1901 dictionary context + version tracking |
| 8. Typeset | `typeset.py` | Bilingual HTML with facing pages, source scan overlay, revision marginalia |

## Setup

```bash
# Install dependencies
uv sync
uv run python -m spacy download it_core_news_lg
```

Create a `.env` file (gitignored):

```
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=...
```

## Usage

```bash
# Full pipeline
uv run python pipeline.py

# Individual steps
uv run python pipeline.py --step download
uv run python pipeline.py --step reconcile
uv run python pipeline.py --step cleanup --llm-cleanup
uv run python pipeline.py --step translate
uv run python pipeline.py --step typeset
```

### Translation refinement

Reviews existing translations against the Edgren 1901 Italian-English Dictionary, making targeted period-appropriate word choice corrections. Full snapshots before each pass enable revert to any prior version.

```bash
# Refine specific chapters
uv run python pipeline.py --step refine --chapter p1_capitolo_primo

# Refine all chapters
uv run python pipeline.py --step refine

# Revert a chapter to a prior version
uv run python pipeline.py --step refine --revert-to 1 --chapter p1_capitolo_primo

# Revert all chapters
uv run python pipeline.py --step refine --revert-to 1
```

### Typesetting

Generates a bilingual HTML edition with:
- Loeb Classical Library-style facing pages (Italian left, English right)
- Slide-in source scan overlay linked to Internet Archive page images
- QR codes per chapter for viewing scans on a second device (phone/tablet)
- Revision marginalia showing tracked translation changes (toggle with the pencil button, navigate with `m` / `Shift+m`)

```bash
# Production (QR codes link to GitHub Pages)
uv run python pipeline.py --step typeset

# Local development (QR codes link to localhost:8000)
uv run python pipeline.py --step typeset --local

# Custom domain
uv run python pipeline.py --step typeset --site-base https://perlaliberta.com
```

For local testing, start the dev server:

```bash
uv run serve.py
```

Then open `http://localhost:8000`. QR codes scanned from a phone on the same network will open the scan viewer at `localhost:8000/scan.html#PAGE-PAGE`.

### Deploying to GitHub Pages

The `docs/` directory contains the deployable site. After typesetting:

```bash
cp output/bilingual.html docs/index.html
cp output/scan.html docs/scan.html
cp static/bilingual.css docs/static/bilingual.css
cd docs && git add -A && git commit -m "Update edition" && git push
```

## Reference dictionaries

Two period-appropriate dictionaries complement the pipeline:

- **Zingarelli 1922** (*Vocabolario della Lingua Italiana*, 2nd ed.) — validates Italian word existence during cleanup and adjudication. Chunked in `assets/dictionary/zingarelli_1922/`.
- **Edgren 1901** (*Italian and English Dictionary*) — provides period-appropriate Italian-to-English translations for the refine and translate steps. Chunked in `assets/dictionary/edgren_1901/`.

Both are public domain OCR from Internet Archive, downloaded automatically on first use.

## Project structure

```
pipeline.py              # CLI orchestrator
download.py              # Fetch OCR texts from Internet Archive
ocr.py                   # Gemini Flash/Pro OCR
reconcile.py             # Dual-source alignment + word-level reconciliation
triage.py                # LLM triage of flagged disagreements
cleanup.py               # OCR artifact removal + LLM correction
adjudicate.py            # Zingarelli-based hyphen classification
validate.py              # Assertion checks on cleaned output
translate.py             # Claude API translation with resume
refine.py                # Edgren-based translation refinement + version tracking
edgren.py                # Edgren 1901 dictionary integration
typeset.py               # Bilingual HTML/PDF generation
utils.py                 # Shared utilities

data/                    # Working files (downloads, intermediate outputs)
output/                  # Final Italian + English markdown, HTML, scan viewer
state/                   # Translation progress, per-chapter files, revision snapshots
assets/                  # Fonts, dictionaries, page images
static/                  # CSS
docs/                    # GitHub Pages deployment (index.html, scan.html, assets)
```

## Source

- LOC scan: [archive.org/details/perlalibertdal00cres](https://archive.org/details/perlalibertdal00cres)
- Google/Harvard scan: [archive.org/details/perlalibertdal00cresuoft](https://archive.org/details/perlalibertdal00cresuoft)
