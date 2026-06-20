# Agent Prompts: Vintage Italian Book Digitization Pipeline

> **⚠️ Superseded design sketch — not the shipped pipeline.** This is an early,
> pre-implementation planning brief written for a *two-witness* design. The built
> *Per la Libertà* pipeline diverges from it in most specifics: it reconciles
> **three** OCR witnesses (`reconcile.py`), aligns with `difflib.SequenceMatcher` +
> `rapidfuzz` (not diff-match-patch / minineedle / collatex / unidecode), corrects
> with `symspellpy`, lemmatizes with **`it_core_news_lg`** (not `it_core_news_sm`),
> uses the three-dictionary oracle (Zingarelli 1922 / Edgren 1901 / Hoare 1915, not
> Edgren alone), and resolves witness disagreements at the triage stage rather than
> via inline `<ed1>/<ed2>` tags. See `CLAUDE.md` and `PIPELINE.md` for the actual
> 11-step architecture. Kept for provenance; do not treat as current guidance.

---

## Prompt 1: OCR Text Reconciliation

We have two OCR text files of the same vintage Italian book, produced from scans of different physical editions. The goal is to produce a single, best-possible unified text by aligning and reconciling the two versions.

### Key techniques to use (in order of priority):

**Normalization (do this first):** Before alignment, normalize both texts to prevent structural noise from polluting the diff.
- *De-hyphenation:* Use a regex to identify and join words split by line breaks (e.g., `word-\nbreak` or `word- \nbreak`). Pattern: `r'(\w+)-\s*\n\s*(\w+)'` → join as `\1\2`. Run this on both texts before any alignment step.
- *Diacritic folding for comparison:* Use `unidecode` to create a comparison-only copy of each text where `ò`, `o'`, and `ó` all reduce to `o`. Feed the folded versions to the diffing engine, but map results back to the original characters for output. This prevents diacritic OCR inconsistencies from registering as differences.

**Alignment:** Use `diff-match-patch` (pip install diff-match-patch) as the primary alignment tool. It implements Myers' diff algorithm with semantic cleanup and fuzzy matching — critical because both texts contain OCR errors, so exact matching will miss valid correspondences. Use `diff_cleanupSemantic()` after every `diff_main()` call to remove coincidental character-level matches that pollute the diff.

For longer texts or when structural divergence is large (different page breaks, missing sections), fall back to Smith-Waterman local alignment. The `minineedle` package (pip install minineedle) implements this for arbitrary Python iterables — tokenize into words and align word sequences, not characters.

**Fuzzy token matching:** Use `rapidfuzz` (pip install rapidfuzz) for word-level comparison when the differ reports a substitution. `fuzz.ratio()` on the two word candidates tells you whether it's a genuine textual difference between editions or just OCR noise on the same word. Threshold: ratio > 80 is likely the same word with OCR errors; ratio < 60 is likely a genuine edition difference.

**Consensus voting:** Where the two witnesses disagree at the character level on what is likely the same word (rapidfuzz ratio > 80), apply character-level alignment and pick the more plausible reading. Heuristics for "more plausible":
- Prefer the reading that forms a valid Italian word (use a word list or `spacy` Italian model for validation)
- Prefer the reading with fewer common OCR confusion patterns (rn→m, cl→d, li→h, fi→fi ligature errors)
- If both readings are valid Italian words, flag for human review

**Collation (optional, for deeper analysis):** `collatex` (pip install collatex) is purpose-built for comparing variant witnesses of the same text. It detects transpositions (text that moved between editions) that diff tools see as unrelated add/delete pairs. Use it if you suspect the editions have reordered passages. It follows the Gothenburg Model: tokenize → normalize → align → analyze → visualize.

### Workflow:

1. Chunk both texts into aligned page/paragraph units (use chapter headings, page markers, or paragraph breaks as anchors)
2. For each chunk pair, run `diff-match-patch` alignment
3. Classify each diff region: OCR noise (fuzzy match > 80) vs. edition difference (fuzzy match < 60) vs. ambiguous (60-80)
4. For OCR noise regions: apply consensus voting to pick the best reading
5. For edition differences: preserve both readings with simple XML-style tags: `<ed1>testo</ed1><ed2>testo</ed2>`. The downstream translation LLM is instructed to use the reading that best fits the grammatical and historical context (informed by the 1901 dictionary definitions). This avoids forcing premature resolution at the reconciliation stage.
6. For ambiguous regions: flag for review
7. Output: a single unified text with inline annotations where the witnesses diverged

### Dependencies:
```
pip install diff-match-patch rapidfuzz minineedle spacy unidecode
python -m spacy download it_core_news_sm
```

---

## Prompt 2: Period-Appropriate Translation Validation Using 1901 Dictionary

We need a lightweight validation check for Italian→English translations to catch anachronistic word choices. Modern LLMs default to contemporary meanings, but our source text is from the late 19th / early 20th century. Word meanings shift over time.

### The resource:

The Edgren Italian-English Dictionary (1901), full OCR text available at:
```
https://archive.org/download/cu31924019173982/cu31924019173982_djvu.txt
```

This is a ~4.6MB raw text file. The OCR is noisy (dense two-column dictionary layout, abbreviations, diacritics) but readable by an LLM without preprocessing.

### What to build:

**Step 1 — Download and chunk the dictionary text.**

Download the file once and save it locally. Split it into chunks that can be searched — simplest approach is line-by-line, but a better heuristic is to split on patterns that look like headword entries. Italian dictionary headwords typically appear as a capitalized or bold word at the start of a line, often followed by a comma or parenthetical pronunciation guide. A rough regex like `r'^[A-Z][a-zàèéìòù]+,'` will catch many headwords, even through OCR noise. Don't try to parse the entries into structured fields — just identify the approximate start of each entry so you can extract a raw text window around a headword.

**Step 2 — Build a simple lookup function.**

Given an Italian word, find the closest matching headword in the dictionary text and return the raw text of that entry (the headword line plus the next N lines until the next headword). Use `rapidfuzz.process.extractOne()` against the list of detected headwords for fuzzy matching — the query word itself may be OCR'd and slightly garbled.

**Lemmatize before lookup.** Italian is highly inflected — a verb like *scuotevano* won't appear in the dictionary, but its lemma *scuotere* will. Use `spacy`'s `it_core_news_sm` to reduce inflected forms to their lemma before searching. This is essential for verbs and plural nouns.

```python
import rapidfuzz
import spacy

nlp = spacy.load("it_core_news_sm")

def lookup_1901(word: str, headwords: list, raw_chunks: dict) -> str | None:
    """Return raw 1901 dictionary entry for an Italian word, or None."""
    # Lemmatize: ebbe → avere, scuotevano → scuotere
    doc = nlp(word)
    lemma = doc[0].lemma_
    
    # Try lemma first, fall back to original form
    match = rapidfuzz.process.extractOne(lemma, headwords, score_cutoff=75)
    if not match:
        match = rapidfuzz.process.extractOne(word, headwords, score_cutoff=75)
    if match:
        return raw_chunks[match[0]]
    return None
```

**Step 3 — Use it as LLM context during translation.**

When translating an Italian passage, for each semantically significant word (nouns, verbs, adjectives — skip function words), look it up in the 1901 dictionary. If found, include the raw entry in the translation prompt:

```
You are translating the following Italian passage from approximately 1900.
For the word "{word}", the 1901 Edgren Italian-English Dictionary provides
this entry (raw OCR, may contain minor errors):

---
{raw_dictionary_entry}
---

Use this period-appropriate definition to inform your translation. If the
modern meaning differs from the 1901 meaning, prefer the 1901 meaning
unless context clearly indicates otherwise. Flag any word where you chose
the period meaning over the modern meaning.
```

That's it. No structured parsing, no embeddings, no vector store. The LLM interprets the messy dictionary entry, compares it against its own knowledge, and adjusts. The dictionary text acts as a grounding constraint.

### What NOT to build:

- Don't parse dictionary entries into structured JSON with sense numbers, POS tags, etc. The LLM handles unstructured dictionary text natively.
- Don't build a semantic similarity comparison between the 1901 definition and the proposed translation. Just give the LLM both and let it reason.
- Don't try to fix the dictionary's OCR first. The noise level is tolerable for an LLM reader. Spending time on dictionary OCR correction is a trap.

### Dependencies:
```
pip install rapidfuzz spacy
python -m spacy download it_core_news_sm
```

---

## Prompt 3: Putting It Together

The full pipeline is:

1. **Reconcile** the two OCR witnesses into a single best Italian text (Prompt 1)
2. **Translate** passages using an LLM, with the 1901 dictionary as a contextual validation source (Prompt 2)
3. **Review** flagged divergences — both OCR reconciliation ambiguities and translation anachronism warnings — in a single human review pass

Keep these as separate, composable steps. The reconciliation pipeline should output clean Italian text that the translation step consumes. The dictionary lookup is a parameter of the translation step, not a dependency of the reconciliation step.
