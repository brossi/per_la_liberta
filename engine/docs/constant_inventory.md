# M1 Constant / Prompt / Sidecar Inventory

Grep-backed inventory of every book/language/scan-specific constant in the top-level
*Per la Libertà!* pipeline, with the config destination each is routed to. This is the
**M1 acceptance checklist** mandated by `ENGINE_FRAMEWORK_PLAN.md` ("Before M1, rebuild
this table as a complete grep-backed constant + prompt + sidecar inventory"): a constant
that ships in the engine core without a destination here is a defect.

Destinations follow the plan's parameterization map (plan §"Config model"). Where this
inventory refines the plan, it is noted inline. Line numbers are against the live tree at
M1 time; they are anchors, not contracts.

## Sources / acquisition

| Constant (file:line) | Type | Encodes | → Destination |
|---|---|---|---|
| `COPY1_URL` (download.py:6) | str | IA URL, LOC/Tesseract copy | `manifest.sources[]` |
| `COPY2_URL` (download.py:7) | str | IA URL, Google/Harvard copy | `manifest.sources[]` |
| `IA_ITEM_ID` (translate.py:414, typeset.py:13) | str | `perlalibertdal00cres` for scan citations | `manifest.sources[]` |

## Scan (book-specific scan facts)

| Constant (file:line) | Type | Encodes | → Destination |
|---|---|---|---|
| `DEFAULT_PDF` (ocr.py:17) | str | LOC source-PDF filename | `manifest.scan` |
| page-image scheme `page_NNNN.png` | str | rendered-page filename template | `manifest.scan` |
| `SCAN_LEAF_OFFSET` (typeset.py:17) | int | scan leaf − book page = 6 | `manifest.scan` |
| `_last_scan_page` fallback (typeset.py:731, dflt 278) | int | last scan leaf | `manifest.scan` (the one scalar inside `chapter_start_pages.json`) |

## Scan-noise profile (reusable source-typeface OCR profile → `profiles/source_noise/bodoni_didone.json`, the `SourceNoiseProfile`)

| Constant (file:line) | Type | Encodes | → Destination |
|---|---|---|---|
| `SUBSTITUTION_RULES` (cleanup.py:20–47, 21 entries) | list[tuple] | Italian-word OCR fix table | `SourceNoiseProfile` *(plan §"Scan/typeface noise"; not period_dictionaries)* |
| `BOUNDARY_SUBSTITUTIONS` (cleanup.py:76–78) | dict | Bodoni `i→r`,`i→e` hyphen-boundary subs | `SourceNoiseProfile` |
| `NOISE_LINE_PATTERN` (cleanup.py:14–16) | regex | OCR noise-line filter | `SourceNoiseProfile` |
| `PAGE_MARKER` (ocr.py:20), page-marker regex (cleanup.py/validate.py `\d+\s+[35][EI]:?`) | str/regex | page-marker artifact shape | `SourceNoiseProfile` |
| `BOUNDARY_SUBS` (adjudicate.py:22) | dict | dup of cleanup boundary subs | `SourceNoiseProfile` (single source) |

`NOISE_LINE_PATTERN`, `_HYPHEN_TOKEN_RE`, `_ACCENT_MAP`, `PAGE_MARKER_RE`, `MID_NOISE`,
`MID_CAPS`, `CONSONANT_CLUSTER` mechanics are **code defaults** — only their *data* (the
substitution/marker tables, the cluster alphabet) is config. `CONSONANT_CLUSTER`'s Italian
consonant set is `LanguageProfile`; the regex shape stays code.

## Structure

| Constant (file:line) | Type | Encodes | → Destination |
|---|---|---|---|
| ≥3 H2, ==57 H3 (24 P1 + 33 P2), 58 units w/ prefazione (validate.py:16–19) | int | header-count contract | `manifest.structure` |
| retention 0.60 (validate.py) | float | cleanup word-loss tolerance | `manifest.structure` *(threshold; plan groups validate thresholds as structure/manifest config)* |
| foreign-char 0.5%, word-quality gate (validate.py) | float | validation thresholds | `manifest.structure` |

## Prompt context (book/era/entities → `manifest.prompt_context`, rendered into `profiles/prompts/*.j2`)

| Constant (file:line) | Encodes | → Destination |
|---|---|---|
| `OCR_PROMPT` (ocr.py:27–38) | book identity in OCR instructions | `manifest.prompt_context` |
| `TRIAGE_SYSTEM` (triage.py:59–80) | Crespi/Italian-OCR triage context | `manifest.prompt_context` |
| `SYSTEM_PROMPT` (translate.py:65–79) | book/era/entities (Orsini, Mazzini, Radetzky, di Rudio, Risorgimento) | `manifest.prompt_context` |
| multi-eval / synthesis / provenance rubric wording (multi_translate.py) | this-book literary rubric | `manifest.prompt_context` |
| Edgren dictionary-context fragment (providers.py, translate.py:101–108) | period-dict prompt block | neutral hook driven by `LanguageProfile.period_dictionaries` |

## Edition (bibliographic + deploy)

| Constant (file:line) | Encodes | → Destination |
|---|---|---|
| title/subtitle/author/colophon, assemble_translation front-matter (translate.py:370–379, typeset.py) | bibliographic metadata | `manifest.edition` |
| `SITE_BASE` (typeset.py:14) | deploy base URL | `manifest` top-level (edition/deploy field) *(plan line 119)* |
| `FONT_DIR`/`CSS_PATH` (typeset.py:18–19), `docs/assets/fonts/` | output font/CSS paths | `OutputTypefaceProfile` → `profiles/typefaces/spectral_fraunces.json` |

## Language profile (Italian ~1900–1922 → `profiles/languages/italian_1900_1922.json`)

| Constant (file:line) | Encodes | → Destination |
|---|---|---|
| `it_core_news_lg` (cleanup.py:67 +4 sites) | spaCy model id | `LanguageProfile.spacy_model` |
| `it_combined.txt` (cleanup.py:56,90) | freq dictionary + word-set | `LanguageProfile.frequency_dictionary` |
| accento-facoltativo accent-skip rule | accent-only-change skip | `LanguageProfile` |
| `ENGLISH_MARKERS`/`SKIP_WORDS` (validate.py:221–232) | leak markers + function-word skips | `LanguageProfile` |
| consonant-cluster alphabet (validate.py:235) | Italian cluster set | `LanguageProfile.consonant_alphabet` |
| char-coverage alphabet (validate.py:134, accented vowels `àèìòùéÀÈÌÒÙÉ`) | language's non-ASCII orthographic letters (the rest of the coverage class is generic punctuation, code) | `LanguageProfile.accented_letters` |
| Zingarelli/Edgren/Hoare dirs + IA URLs (adjudicate.py:19, edgren.py:16–23, hoare.py:30–39) + ≥2-of-3 oracle | period dictionaries | `LanguageProfile.period_dictionaries[]` + `oracle_min` |

## LanguagePlugin code (`lang/italian.py` — Italian, not data-only)

| Constant (file:line) | Encodes | → Destination |
|---|---|---|
| `ORDINALS` (utils.py:13–24, 33), `COMPOUND_ORDINALS` (51–69, 19), `ORDINAL_FIXES` (28–40, 10), `WORD_FIXES` (43–48, 4) | word→int ordinal parsing + OCR-garble fixes | `lang/italian.py` *(plan line 127 routes all four here; the garble fixes are observed-OCR data the plugin owns)* |
| heading regex `(?:[GC][a-z]*pitolo|Capitolo)…` (utils.py:209) | chapter-heading detection | `lang/italian.py` |
| structural markers `PREFAZIONE`/`PARTE SECONDA`/`FINE DELLA PRIMA PARTE`/`PER LA LIBERTA` (utils.py:249–266) + `parse_italian_markdown` book-title/part titles (translate.py:29–42) | part/structure recognition | `lang/italian.py` |
| `_ITALIAN_NUMBERS`/`_ITALIAN_ORDINAL_PARTS`/teens + `_italian_to_english_title` (translate.py:297–361) | Italian title → English | `lang/italian.py` |
| `strip_boilerplate` PREFAZIONE…INDICE markers (utils.py:138–156) | boilerplate bounds | `lang/italian.py` |

## Sidecars (per-book; `books/<id>/`, covered by the sidecar-contracts track, not flattened to scalars)

| Sidecar | Key scheme | Reader/writer |
|---|---|---|
| `typography.json` | parse_md id (`p1_capitolo_decimo_ottavo`) | typeset reads (typography.py) |
| `chapter_start_pages.json` | **parse_md id** (verified: keys are `p1_capitolo_primo`…); holds `_last_scan_page` scalar | typeset reads; no code writes |
| `chapter_pages.json` | **short id** (verified: keys are `p1_ch01`…) | reconcile writes, cleanup reads |
| `source_pages.json` | parse_md id | translate writes, typeset reads |

## Chapter-identity namespaces (the M1 tripwire — three derivations, sequential-per-part join)

| Form | Derivation (live code) | Example (P1 ch1 / prefazione) |
|---|---|---|
| `short` | `split_into_chapters` ordinal parse → `p{part}_ch{NN}` (utils.py:278); keys `chapter_pages.json` | `p1_ch01` / `prefazione` |
| `parse_md` | `parse_italian_markdown` → `{p1\|p2\|''}_` + `re.sub(r"[^a-z0-9]","_",title.lower())` (translate.py:44–45); keys `chapter_start_pages.json`, `typography.json`, translate state | `p1_capitolo_primo` / `prefazione` |
| `html_slug` | `_slug(part_it)`-`_slug(title_it)`, hyphenated (typeset.py:143,924–925); HTML anchors | `parte-prima-capitolo-primo` / `prefazione` |
| `english_title` | `_italian_to_english_title` (translate.py:322) | `Chapter One` / `Preface` |
| `page_range` | `chapter_start_pages.json[parse_md].start_scan` → next−1 (typeset.py:732–735) | `(9,14)` / `(7,8)` |

All move into a single `ChapterIdentity` produced by the `LanguagePlugin`, breaking the
`utils`→`translate` import cycle. `test_chapterids_golden` freezes every PLL form and
asserts the plugin reproduces them without calling live top-level code at test time.

## Resolved against the plan (no open decisions)

The sub-agent inventory flagged a few items as "ambiguous"; the plan already decides them,
so M1 follows the plan, not a re-litigation:
- `SUBSTITUTION_RULES`/boundary subs → **SourceNoiseProfile** (plan §"Scan/typeface noise"), not a dictionary.
- ordinal OCR-garble fixes (`qyinto`…) → **`lang/italian.py`** with the canonical ordinals (plan line 127), even though they are observed-scan data; the plugin owns them.
- `SITE_BASE` → **manifest top-level** deploy field (plan line 119).
- validate structure counts/thresholds → **`manifest.structure`** (plan line 120).
