# Per la Libertà! / For Freedom!

English translation of *Per la Libertà! (Dalle mie conversazioni col Conte Carlo di Rudio, complice di Felice Orsini)* by Cesare Crespi (1913). The book documents conversations with Count Carlo di Rudio about Italian unification, the Risorgimento, and the Orsini conspiracy against Napoleon III.

Published by Canessa Printing Co., 708 Montgomery St., San Francisco.

**Live edition**: [brossi.github.io/PER_LA_LIBERTA](https://brossi.github.io/PER_LA_LIBERTA/)

## Pipeline

An 11-step **build** pipeline reconciles two independent physical scans from Internet Archive (OCR'd into three witnesses), cleans artifacts via dictionary validation and LLM correction, translates with a multi-model synthesis, and typesets a bilingual edition — single-language reading view by default, with an opt-in Loeb-style facing-page toggle — plus a Reader's Companion. A separate, ongoing **review** phase (deviation/vision/intention review) audits the finished edition against the 1913 scans — see [`REVIEW.md`](REVIEW.md). Step-by-step detail is in [`PIPELINE.md`](PIPELINE.md).

| Step | File | What it does |
|------|------|-------------|
| 1. Download | `download.py` | Fetches 2 DJVU text copies from Internet Archive (LOC + Google/Harvard) |
| 2. OCR | `ocr.py` | Gemini Flash (page mapping) + Gemini Pro (quality witness) on the LOC PDF scan |
| 3. Reconcile | `reconcile.py` | 2-way paragraph alignment with Copy 3 as word-level adjudicator |
| 4. Triage | `triage.py` | LLM categorization + resolution of remaining disagreements |
| 5. Cleanup | `cleanup.py` | Noise removal, dehyphenation, symspellpy correction, spaCy NER protection |
| 5b. Adjudicate | `adjudicate.py` | Classifies unresolved hyphens via Zingarelli 1922 dictionary |
| 6. Validate | `validate.py` | 7 assertion checks on cleaned output |
| 7. Translate | `translate.py` / `multi_translate.py` | Single-model (Claude Sonnet 4.6) or multi-witness synthesis (`--multi-model`); the live edition used the latter |
| 7b. Refine | `refine.py` | Post-hoc refinement with Edgren 1901 dictionary context + version tracking |
| 8. Typeset | `typeset.py` | Bilingual HTML with facing pages, restored 1913 typography, source scan overlay, revision marginalia |
| 9. Companion | `companion.py` | Renders the hand-authored Reader's Companion to standalone HTML pages + entity/citation JSON indexes |

## Setup

Requires **Python ≥ 3.13** (enforced by `.python-version` / `pyproject.toml`).

```bash
# Install dependencies
uv sync
```

`uv sync` also installs the spaCy Italian model `it_core_news_lg` — it is pinned by wheel URL in `pyproject.toml`, so it is locked rather than pruned. If the model is ever missing, re-fetch it with `uv run python -m spacy download it_core_news_lg`.

Create a `.env` file (gitignored):

```
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=...
# Optional — only for the GPT draft member of multi-model translation
# (--draft-models ...,gpt). Not needed for the default build.
OPENAI_API_KEY=...
```

The **review** phase needs additional keys (`OPENAI_API_KEY` for the comprehension panel/checker, `DEEPL_API_KEY` for neutral MT) — see [`REVIEW.md`](REVIEW.md).

### Source files

Two large scans are **gitignored** and must be placed at the repo root manually (the pipeline does not download them):

- **LOC scan PDF** — `public-gdcmassbookdig-perlalibertdal00cres-perlalibertdal00cres.pdf` (~82 MB), from [archive.org/details/perlalibertdal00cres](https://archive.org/details/perlalibertdal00cres). Required by step 2 (OCR); OCR is silently skipped if it is absent.
- **Harvard/Google scan PDF** — `harvard_perlalibertdall00cresgoog.pdf`, from [archive.org/details/perlalibertdall00cresgoog](https://archive.org/details/perlalibertdall00cresgoog). Required only for the review phase's second-copy vision escalation (`build_concordance.py`, `vision_review.py`).

The DJVU **text** copies (`copy1_raw.txt`, `copy2_raw.txt`) *are* fetched automatically by step 1.

## Usage

`--step` accepts `download`, `ocr`, `reconcile`, `triage`, `cleanup`, `adjudicate`, `validate`, `translate`, `refine`, `typeset`, `companion`, or `all` (default). A selection:

```bash
# Full pipeline (all build steps)
uv run python pipeline.py

# Individual steps
uv run python pipeline.py --step download
uv run python pipeline.py --step reconcile
uv run python pipeline.py --step cleanup --llm-cleanup
uv run python pipeline.py --step translate                      # single-model
uv run python pipeline.py --step translate --multi-model        # multi-witness synthesis (produced the live edition)
uv run python pipeline.py --step typeset
uv run python pipeline.py --step companion
```

Tune the `--multi-model` path with `--draft-models claude,gemini,gpt` and `--synth-model opus|sonnet` (defaults: `claude,gemini` / `opus`).

> **Regeneration guard.** `--step cleanup`, `--step translate`, and `--step all` overwrite committed, hand-tuned text and are blocked: each requires typing a confirmation at an interactive TTY (or `PER_LA_LIBERTA_ALLOW_REGEN=1`) and **hard-aborts (exit 2) for any non-interactive caller**. See the regeneration-guard note in [`CLAUDE.md`](CLAUDE.md). Typesetting (`--step typeset`) is unguarded.

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
- A single-language reading view by default (English), with a **Both / IT / EN** toggle; the **Both** view is the Loeb Classical Library-style facing-page layout (Italian left, English right)
- Restored 1913 typography (italics, bold, small caps, set-off verse) from the scan-verified `data/typography.json` sidecar
- Slide-in source scan overlay linked to Internet Archive page images
- QR codes per chapter for viewing scans on a second device (phone/tablet)
- Revision marginalia showing tracked translation changes (toggle with the pencil button, navigate with `m` / `Shift+m`); page-citation marginalia navigate with `p` / `Shift+p`

```bash
# Production (QR codes link to GitHub Pages)
uv run python pipeline.py --step typeset

# Local development (QR codes link to localhost:8000)
uv run python pipeline.py --step typeset --local

# Custom domain
uv run python pipeline.py --step typeset --site-base https://perlaliberta.com
```

For local testing, start the dev server. It serves the `docs/` directory — i.e. what `--step typeset` synced there, not `output/`:

```bash
uv run python serve.py        # override the port with PORT=8001
```

Then open `http://localhost:8000`. QR codes scanned from a phone on the same network will open the scan viewer at `localhost:8000/scan.html#PAGE-PAGE`.

### Deploying to GitHub Pages

The `docs/` directory is the deployable site, served from `/docs` on `main`. **`--step typeset` already writes `docs/index.html`, `docs/scan.html`, and `docs/static/bilingual.css`** — with the relative-path rewrites a plain `cp` would omit (manually copying `output/bilingual.html` or `static/bilingual.css` reintroduces broken font/CSS/scan-image paths). `--step companion` writes `docs/companion/`. So after building, the only step is to commit the site from the repo root:

```bash
git add docs && git commit -m "Update edition" && git push
```

(`docs/` is part of this repo, not a submodule — don't `cd docs && git add -A`, which would stage the whole tree, including `output/` and `state/`.)

## Reference dictionaries

Three period-appropriate dictionaries complement the pipeline:

- **Zingarelli 1922** (*Vocabolario della Lingua Italiana*, 2nd ed.) — validates Italian word existence during cleanup and adjudication. Chunked in `assets/dictionary/zingarelli_1922/`.
- **Edgren 1901** (*Italian and English Dictionary*) — provides period-appropriate Italian-to-English translations for the refine and translate steps. Chunked in `assets/dictionary/edgren_1901/`.
- **Hoare 1915** (*An Italian Dictionary*, Cambridge) — a third period authority, strong on archaic/literary/technical vocabulary. Chunked in `assets/dictionary/hoare_1915/`.

Together they form a membership oracle used in the review phase: a word recognized by ≥2 of the three is treated as a real period form. All are public domain OCR from Internet Archive. The chunked text every lookup reads is committed to the repo (no fetch needed); Edgren and Hoare can re-download their regenerable raw OCR on demand, while Zingarelli ships chunked with no download path.

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
translate.py             # Single-model Claude translation with resume
multi_translate.py       # Multi-witness synthesis (drafts → evaluate → Opus); the live edition's path
providers.py             # Model-provider abstraction for the draft models
refine.py                # Edgren-based translation refinement + version tracking
edgren.py                # Edgren 1901 dictionary integration
typeset.py               # Bilingual HTML generation
typography.py            # Scan-verified type-restoration sidecar (applied at typeset)
companion.py             # Reader's Companion HTML rendering
serve.py                 # Local preview server for docs/
utils.py                 # Shared utilities
# review-phase scripts (vision_review.py, build_concordance.py, …) are documented in REVIEW.md

data/                    # Working files (downloads, intermediate outputs)
output/                  # Final Italian + English markdown, HTML, scan viewer
state/                   # Translation progress, per-chapter files, revision snapshots
assets/                  # Dictionaries + Harvard (Copy B) page renders; fonts and LOC page images live under docs/assets/
static/                  # CSS (canonical bilingual.css)
docs/                    # GitHub Pages site: index.html, scan.html, companion/, static/, assets/
```

## Source

- LOC scan: [archive.org/details/perlalibertdal00cres](https://archive.org/details/perlalibertdal00cres)
- Google/Harvard scan: [archive.org/details/perlalibertdall00cresgoog](https://archive.org/details/perlalibertdall00cresgoog)
