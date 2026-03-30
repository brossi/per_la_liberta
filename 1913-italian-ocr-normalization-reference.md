# 1913 Italian Typography — OCR Normalization Reference

Context: These are verified concerns for OCR cleanup of early 20th-century Italian printed books. Use this as a reference when building or refining punctuation/normalization passes in the Athanor pipeline.

---

## 1. Accent Normalization (Grave ↔ Acute on final -e)

**Problem:** Pre-mid-20th-century Italian printing did not consistently distinguish grave (è) from acute (é) on word-final e. You will encounter `perchè`, `benchè`, `poichè` where modern standard prescribes `perché`, `benché`, `poiché` (acute, indicating closed /e/).

**What to normalize:** For lemmatization and search, treat grave and acute variants of the same word as identical. For display text, preserve the source form — do not silently "correct" to modern convention, as the grave form reflects period typography, not an error.

**Scope:** The grave/acute ambiguity applies only to final -e. Final -a, -i, -o, -u always take grave in Italian (à, ì, ò, ù).

## 2. Guillemets (« ») — Tokenization

**Problem:** Italian books of this period use «virgolette caporali» (angle quotation marks). Period typography often inserted thin space between the guillemet and the adjacent word: `« Parola »`. OCR frequently tokenizes this as three separate items: `«`, `Parola`, `»`.

**What to normalize:** Strip spaces between guillemets and their enclosed text. Normalize to `«Parola»` (no interior spaces) for consistency, or to your chosen quotation style if converting to a different convention.

**Also watch for:** OCR misreading « as `<`, `<<`, or similar; and » as `>`, `>>`.

## 3. Apostrophe Loss and Misreading

**Problem:** Elided forms are more frequent in this period than modern Italian (e.g., `gl'italiani` for `gli italiani`, `un'altra`, `l'onore`). In metal type, the apostrophe glyph is thin and sits high. In degraded scans or high-contrast OCR:
- Apostrophe disappears entirely: `l'anno` → `lanno`
- Apostrophe misread as comma: `l'anno` → `l,anno`
- Apostrophe misread as backtick or accent: `l'anno` → `` l`anno ``

**What to normalize:** Flag any comma appearing mid-word (between two lowercase alpha sequences) as a probable apostrophe. Flag merged-word patterns that match known elision patterns (e.g., regex for common proclitics: `^[dlnscu](?=[aeiou])` without apostrophe).

## 4. f-Ligature Misreads (fi, fl, ff, ffi, ffl)

**Problem:** In period typography, f + i/l combinations were cast as single metal sorts (ligatures) to prevent the f's hood from colliding with the i's dot or l's ascender. OCR engines that aren't ligature-aware may misread these combined glyphs:
- `fi` → `fi` (correct), but also → `u`, `n`, `ri`, `th`
- `fl` → `fl` (correct), but also → `d`, `tl`
- `ff` → `tf`, `tt`
- `ffi` → `fli`, `tti`

**What to normalize:** If you have a dictionary/wordlist, flag any word containing suspicious `u`, `n`, `ri`, `th` sequences that would make sense as `fi` substitutions (e.g., `difucult` → `difficult`). For Italian specifically, watch for common words: `filosofia`, `efinito`, `difficile`, `affidare`, `conflitto`, etc.

## 5. Dash and Hyphen Normalization

**Problem:** Period Italian books use em-dashes (—) for dialogue attribution and parenthetical statements, typically with spaces on both sides (` — `). OCR commonly produces:
- Double hyphens: `--`
- Triple hyphens: `---`
- Underscore sequences: `___` or `__`
- Mixed: `-—` or `—-`

Line-end hyphens (word breaks) use a standard hyphen (-) and need separate handling from punctuation dashes.

**What to normalize:** Collapse `--`, `---`, and similar sequences into a single em-dash character (U+2014). Distinguish line-end hyphens (rejoin broken words) from intra-sentence dashes (preserve as punctuation). A line-end hyphen followed by a lowercase letter on the next line is almost certainly a word break.

## 6. Additional Period-Specific Watchpoints

- **Circumflex for ii contraction:** Older Italian used ˆ to mark contracted double-i plurals (e.g., `studî` for `studii/studi`). OCR may drop the circumflex or misread it.
- **Long s (ſ):** Gemini claimed this was gone by 1913, which is correct for Italian — but verify against your specific source. If present, OCR will misread ſ as f, l, or t.
- **Spacing around punctuation:** Period convention may include thin spaces before semicolons, colons, question marks, and exclamation marks (French influence). OCR may or may not preserve these.
