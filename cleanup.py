"""Step 3: Clean OCR artifacts and optionally use LLM for Italian text correction."""

import difflib
import json
import logging
import os
import re
import time
from pathlib import Path

log = logging.getLogger(__name__)

# Regex-based OCR artifact patterns to remove or fix
NOISE_LINE_PATTERN = re.compile(
    r"^[\s\d\^IElE\-\*\(\)fr»iiim3S5ZBP\.,:;!?~`@#$%&=+<>{}|\[\]\\/'\"\•\·\°]+$"
)

# High-confidence OCR substitution rules.
# Case-insensitive with case-preserving replacement.
SUBSTITUTION_RULES = [
    # "più" OCR garbles (accent + doubled-i combos)
    (r"piii", "più"),
    (r"pili", "più"),
    (r"piìi", "più"),
    (r"piiì", "più"),
    # Systematic c↔e OCR confusion (Copy 1 scanner artifact)
    (r"cbe", "che"),
    (r"cbi", "chi"),
    (r"eolla", "colla"),
    (r"eol", "col"),
    (r"eome", "come"),
    (r"eosa", "cosa"),
    (r"eosì", "così"),
    (r"eosl", "così"),
    (r"eui", "cui"),
    (r"easa", "casa"),
    (r"earo", "caro"),
    (r"ealdo", "caldo"),
    (r"eentro", "centro"),
    (r"eontro", "contro"),
    # h↔b confusion
    (r"bo", "ho"),
    # Other systematic substitutions
    (r"salla", "sulla"),
    # Digit/letter confusion
    (r"5AN", "SAN"),
]


def _get_spellchecker():
    """Lazy-load symspellpy with Italian frequency dictionary."""
    if not hasattr(_get_spellchecker, "_sym"):
        from symspellpy import SymSpell

        sym = SymSpell(max_dictionary_edit_distance=2, prefix_length=7)
        dict_path = Path(__file__).parent / "data" / "dictionaries" / "it_combined.txt"
        sym.load_dictionary(str(dict_path), term_index=0, count_index=1)
        _get_spellchecker._sym = sym
    return _get_spellchecker._sym


def _get_ner_nlp():
    """Lazy-load spaCy Italian model with NER enabled."""
    if not hasattr(_get_ner_nlp, "_nlp"):
        import spacy

        _get_ner_nlp._nlp = spacy.load("it_core_news_lg", disable=["parser", "lemmatizer"])
    return _get_ner_nlp._nlp


# OCR confusion pairs observed at line-break boundaries in Bodoni typeface.
# Maps OCR-misread character → list of likely intended characters.
# - r→i: dominant pattern; Bodoni's 'r' is a short vertical stroke whose
#         top-right flag is lost at scan edges, reading as 'i'
# - e→i: Bodoni 'e' and 'i' differ only in the crossbar
BOUNDARY_SUBSTITUTIONS: dict[str, list[str]] = {
    "i": ["r", "e"],
}

# Pattern matching letter-hyphen-letter tokens (Unicode-aware).
# Each side must be ≥2 chars: Italian syllabification never produces
# single-char fragments, so 1-char sides are always OCR noise.
_HYPHEN_TOKEN_RE = re.compile(r"([a-zA-ZÀ-ÿ]{2,})-([a-zA-ZÀ-ÿ]{2,})")


def _get_word_set() -> set[str]:
    """Lazy-load the Italian dictionary as a plain set for O(1) membership checks."""
    if not hasattr(_get_word_set, "_words"):
        words = set()
        dict_path = Path(__file__).parent / "data" / "dictionaries" / "it_combined.txt"
        with open(dict_path, encoding="utf-8") as f:
            for line in f:
                parts = line.split()
                if parts:
                    words.add(parts[0].lower())
        _get_word_set._words = words
    return _get_word_set._words


def _in_word_set(word: str, word_set: set[str]) -> bool:
    """Check dictionary membership, accent-insensitive.

    The 1913 text uses accento facoltativo liberally and OCR sometimes
    introduces spurious accents. We accept a match if the accent-stripped
    form exists in the dictionary.
    """
    lower = word.lower()
    if lower in word_set:
        return True
    stripped = _strip_accents(lower)
    return stripped != lower and stripped in word_set


def dehyphenate_token(left: str, right: str, word_set: set[str]) -> str | None:
    """Try to rejoin a hyphenated token, returning the corrected form or None.

    Multi-pass strategy:
      1. Simple join — check dictionary
      2. OCR substitution at last 1-2 chars of left half
      3. OCR substitution at first 1-2 chars of right half
      4. Drop duplicated character at boundary (OCR sometimes doubles a char
         across the break, e.g. 'sottosta-ati' from 'sottostati')

    Returns the joined word if any pass succeeds, else None.
    """
    # Pass 1: simple join
    joined = left + right
    if _in_word_set(joined, word_set):
        return joined

    # Pass 2: substitute at the end of the left half (last 2 chars)
    for pos in range(max(0, len(left) - 2), len(left)):
        ch = left[pos].lower()
        if ch in BOUNDARY_SUBSTITUTIONS:
            for replacement in BOUNDARY_SUBSTITUTIONS[ch]:
                candidate = left[:pos] + replacement + left[pos + 1:] + right
                if _in_word_set(candidate, word_set):
                    return candidate

    # Pass 3: substitute at the start of the right half (first 2 chars)
    for pos in range(min(2, len(right))):
        ch = right[pos].lower()
        if ch in BOUNDARY_SUBSTITUTIONS:
            for replacement in BOUNDARY_SUBSTITUTIONS[ch]:
                candidate = left + right[:pos] + replacement + right[pos + 1:]
                if _in_word_set(candidate, word_set):
                    return candidate

    # Pass 4: drop a spurious boundary character.
    # 4a: OCR sometimes reads 'r' as 'ri', inserting an extra 'i' at the
    #     break (e.g. 'assicuri-azioni' from 'assicurazioni').
    if len(left) > 1 and left[-1].lower() == "i":
        candidate = left[:-1] + right
        if _in_word_set(candidate, word_set):
            return candidate
    if len(right) > 1 and right[0].lower() == "i":
        candidate = left + right[1:]
        if _in_word_set(candidate, word_set):
            return candidate
    # 4b: duplicated character at the join boundary — the OCR may have
    #     doubled a char across the line break (e.g. 'sottosta-ati').
    if (len(left) > 1 and len(right) > 1
            and left[-1].lower() == right[0].lower()
            and left[-1].lower() != "i"):  # already handled in 4a
        candidate = left[:-1] + right
        if _in_word_set(candidate, word_set):
            return candidate
        candidate = left + right[1:]
        if _in_word_set(candidate, word_set):
            return candidate

    return None


def dehyphenate_text(text: str, word_set: set[str] | None = None) -> tuple[str, list[dict]]:
    """Fix mid-line hyphenated tokens where joining produces a valid Italian word.

    Returns (corrected_text, flags) where flags is a list of unresolved
    hyphenated tokens for sidecar output.
    """
    if word_set is None:
        word_set = _get_word_set()

    flags: list[dict] = []

    def _replacer(m: re.Match) -> str:
        left, right = m.group(1), m.group(2)

        # Skip if either side is purely digits (dates like 1848-1849)
        if left.isdigit() or right.isdigit():
            return m.group(0)

        result = dehyphenate_token(left, right, word_set)
        if result is not None:
            log.info("Dehyphenated: %s-%s → %s", left, right, result)
            return result

        # Unresolved — flag for sidecar with classification hint
        has_nonalpha = any(
            not c.isalpha() and c != "-" for c in m.group(0)
        )
        both_caps = left[0].isupper() and right[0].isupper()
        if has_nonalpha:
            reason = "ocr_noise"
        elif both_caps:
            reason = "ner_candidate"
        else:
            reason = "unresolved"
        flags.append({
            "token": m.group(0),
            "left": left,
            "right": right,
            "offset": m.start(),
            "reason": reason,
        })
        return m.group(0)

    corrected = _HYPHEN_TOKEN_RE.sub(_replacer, text)
    return corrected, flags


def is_noise_line(line: str) -> bool:
    """Check if a line is purely OCR decoration/noise."""
    stripped = line.strip()
    if not stripped:
        return False
    # Pure digits (page numbers)
    if re.match(r"^\d+$", stripped):
        return True
    # Very short non-word lines
    if len(stripped) <= 4 and not re.match(r"^[a-zA-ZàèìòùéÀÈÌÒÙ]+$", stripped):
        return True
    # Noise patterns
    if NOISE_LINE_PATTERN.match(stripped):
        return True
    # Lines with very low ratio of letters to non-letters
    letters = sum(1 for c in stripped if c.isalpha())
    if len(stripped) > 3 and letters / len(stripped) < 0.3:
        return True
    # Page marker artifacts: short lines with digits and OCR noise like "3E", "ÌE", "se:", etc.
    if re.match(r"^[\s\dA-Z\-\*\(\):;,.!?ÌÈàèìòùéE3S5asgioelIcruhknwm\^]+$", stripped) and len(stripped) < 30:
        # Check if it has more digits/noise than real words
        words = stripped.split()
        real_words = [w for w in words if re.match(r"^[a-zA-ZàèìòùéÀÈÌÒÙ]{3,}$", w)]
        if len(real_words) <= 1 and any(c.isdigit() for c in stripped):
            return True
    # Lines that are OCR page separator patterns
    if re.match(r"^[-\s\dEeISsBa3Ì5:;\(\)\^»«fr]+$", stripped):
        return True
    # Fascicle/dispensa markers: "Disp. I", "Diip. 3", etc.
    if re.match(r"^Di[si]p\.?\s+[IVX0-9]+$", stripped, re.IGNORECASE):
        return True
    # Short mixed alphanumeric fragments with digits but no real words
    # (e.g. "3HE I98fflE;", "fi 27 n.", "3ìf 260 w:")
    if len(stripped) < 30 and any(c.isdigit() for c in stripped):
        words = stripped.split()
        real_words = [w for w in words if re.match(r"^[a-zA-ZÀ-ÿ]{4,}$", w)]
        if not real_words:
            return True
    # Short lines with high special-character density
    # (e.g. "3? fi-\"k5P.,", "%^ >o 3DC.")
    if 3 < len(stripped) < 20:
        special = sum(1 for c in stripped if not c.isalnum() and not c.isspace())
        if special / len(stripped) > 0.4:
            return True
    return False


_ACCENT_MAP = str.maketrans(
    "àáâèéêìíîòóôùúûÀÁÂÈÉÊÌÍÎÒÓÔÙÚÛ",
    "aaaeeeiiiooouu" + "u" + "AAAEEEIIIOOOUU" + "U",
)


def _strip_accents(text: str) -> str:
    """Remove accent marks from vowels for comparison."""
    return text.translate(_ACCENT_MAP)


def _is_accent_only_change(original: str, corrected: str) -> bool:
    """Return True if the only difference between original and corrected is accent removal."""
    return _strip_accents(original) == _strip_accents(corrected)


def _case_preserving_sub(pattern: str, replacement: str, text: str) -> str:
    """Apply a regex substitution preserving the original's capitalization."""
    def _replacer(match):
        original = match.group(0)
        if original[0].isupper():
            return replacement[0].upper() + replacement[1:]
        return replacement
    return re.sub(r"\b" + pattern + r"\b", _replacer, text, flags=re.IGNORECASE)


def apply_pre_filters(text: str) -> str:
    """Apply high-confidence regex pre-filters for systematic OCR patterns."""
    for pattern, replacement in SUBSTITUTION_RULES:
        text = _case_preserving_sub(pattern, replacement, text)
    return text


# Punctuation normalization rules: (compiled_regex, replacement)
# Order matters — garbled quote patterns before doubled punctuation.
_PUNCT_RULES: list[tuple[re.Pattern, str]] = [
    # Spaced single-quote pairs → double quote (OCR misread of curly quotes).
    # Closing ' ' (preceded by word/punct on same line): consume leading space
    (re.compile(r"(?<=[\w.,;:!?]) +'\s+'"), '"'),
    # Opening ' ' (followed by a word on same line): consume trailing space
    (re.compile(r"'\s+' +(?=\w)"), '"'),
    # Remaining ' ' (no clear context)
    (re.compile(r"'\s+'"), '"'),
    # Caret or asterisk + quote combos → double quote
    (re.compile(r"[\^*]\s*'"), '"'),
    # Asterisk pairs → double quote
    (re.compile(r"\*\s*\*"), '"'),
    # Runs of 2+ same punctuation → single (with optional whitespace
    # between, since the spacing fix later may not have run yet)
    (re.compile(r"(?:;\s*){2,};?"), ";"),
    (re.compile(r"(?:,\s*){2,},?"), ","),
    (re.compile(r"(?::\s*){2,}:?"), ":"),
    # Stray guillemets → double quote (not used in the 1913 original)
    (re.compile(r"[«»]"), '"'),
    # Guillemet OCR misreads (angle brackets)
    (re.compile(r"<<"), '"'),
    (re.compile(r">>"), '"'),
    # Mid-word comma → apostrophe (thin apostrophe glyph misread as comma)
    (re.compile(r"(?<=[a-zA-ZÀ-ÿ]),(?=[a-zA-ZÀ-ÿ])"), "'"),
    # Mid-word backtick → apostrophe
    (re.compile(r"(?<=[a-zA-ZÀ-ÿ])`(?=[a-zA-ZÀ-ÿ])"), "'"),
    # Double/triple hyphens → em-dash
    (re.compile(r"-{2,}"), "—"),
    # Stray caret between words — OCR noise from Bodoni decorative elements
    (re.compile(r"(?<=\w)\s+\^\s+(?=\w)"), " "),
]


def normalize_punctuation(text: str) -> tuple[str, int]:
    """Normalize OCR-garbled punctuation marks.

    The 1913 book uses typographic double quotation marks and em-dashes for
    dialogue. OCR witnesses frequently misread these as spaced single-quote
    pairs, doubled punctuation, or caret/asterisk noise.

    Returns (normalized_text, total_replacements).
    """
    total = 0
    for pattern, replacement in _PUNCT_RULES:
        text, n = pattern.subn(replacement, text)
        total += n
    return text, total


def apply_dictionary_correction(text: str) -> str:
    """Use symspellpy for dictionary-based OCR correction with spaCy tokenization.

    spaCy splits Italian contractions at the apostrophe (e.g., dell'Italia →
    ["dell'", "Italia"]), allowing each part to be corrected independently.
    NER and POS tagging protect proper nouns from false corrections.
    """
    from symspellpy import Verbosity

    sym = _get_spellchecker()
    nlp = _get_ner_nlp()

    def _correct_token(tok_text: str, is_proper: bool) -> str:
        """Correct a single spaCy token using dictionary lookup."""
        # Strip edge punctuation to get the core word
        inner = tok_text.strip(".,;:!?\"'""''«»—-")
        if not inner or not inner[0].isalpha():
            return tok_text
        # Skip protected proper nouns
        if is_proper:
            return tok_text
        # Clitic prefixes ending in apostrophe (dell', l', d', etc.) —
        # these are functional words, not spell-checkable content
        if inner.endswith("'") or inner.endswith("'") or inner.endswith("`"):
            return tok_text
        # Skip very short words (too ambiguous for edit-distance-1)
        if len(inner) <= 2:
            return tok_text

        suggestions = sym.lookup(inner.lower(), Verbosity.TOP, max_edit_distance=1, include_unknown=True)
        if not suggestions:
            return tok_text

        best = suggestions[0]
        # Only correct words NOT already in the dictionary
        if best.distance == 0:
            return tok_text
        if best.distance == 1:
            corrected = best.term
            # If the only difference is accent removal, skip — this could be
            # a legitimate 1913-era stress marking (accento facoltativo), e.g.,
            # pàtria, sècolo, prìncipi. The LLM cleanup pass has sentence
            # context to judge these; symspellpy does not.
            if _is_accent_only_change(inner.lower(), corrected):
                return tok_text
            # Preserve original casing
            if inner[0].isupper():
                corrected = corrected[0].upper() + corrected[1:]
            if inner.isupper():
                corrected = corrected.upper()
            # Re-attach any stripped punctuation
            prefix = tok_text[:tok_text.index(inner[0])] if inner[0] in tok_text else ""
            suffix = tok_text[tok_text.rindex(inner[-1]) + 1:] if inner[-1] in tok_text else ""
            return prefix + corrected + suffix

        return tok_text

    # Process line by line to preserve paragraph structure
    result_lines = []
    for line in text.split("\n"):
        if not line.strip():
            result_lines.append(line)
            continue

        # Use spaCy to tokenize — this correctly splits contractions
        # (dell'Italia → ["dell'", "Italia"]) and tags proper nouns
        doc = nlp(line)

        # Build set of proper noun / named entity token indices.
        # Be conservative: only protect tokens that are BOTH tagged as entities
        # AND either capitalized or tagged as PROPN. OCR-corrupted common words
        # (e.g., "estàte" mistakenly tagged as PER entity for "d'Este") should
        # not be protected.
        proper_indices = set()
        for ent in doc.ents:
            if ent.label_ in ("PER", "LOC", "ORG", "MISC"):
                for i in range(ent.start, ent.end):
                    tok = doc[i]
                    if tok.pos_ == "PROPN" or tok.text[0].isupper():
                        proper_indices.add(i)
        for tok in doc:
            if tok.pos_ == "PROPN" and tok.text[0].isupper():
                proper_indices.add(tok.i)

        # Correct each token and reconstruct with original whitespace
        parts = []
        for tok in doc:
            is_proper = tok.i in proper_indices
            corrected = _correct_token(tok.text, is_proper)
            parts.append(corrected)
            parts.append(tok.whitespace_)

        result_lines.append("".join(parts).rstrip())

    return "\n".join(result_lines)


def join_broken_paragraphs(text: str) -> str:
    """Join paragraphs that were falsely split at OCR page boundaries.

    Heuristic: real Italian paragraphs never start with a lowercase letter.
    If a paragraph starts lowercase, it's a continuation of the previous one.
    Also joins when the previous paragraph ends with a hyphen (broken word).
    """
    paragraphs = text.split("\n\n")
    if len(paragraphs) <= 1:
        return text

    result = [paragraphs[0]]
    for i in range(1, len(paragraphs)):
        prev = result[-1].rstrip()
        curr = paragraphs[i]
        curr_stripped = curr.lstrip()

        if not curr_stripped:
            result.append(curr)
            continue

        first_char = curr_stripped[0]
        should_join = False

        # Case 1: previous ends with hyphen — broken word across page boundary
        if prev.endswith("-"):
            should_join = True
        # Case 2: current starts lowercase — continuation of previous sentence
        elif first_char.islower() or first_char in "àèéìòù":
            should_join = True

        if should_join:
            if prev.endswith("-"):
                # Join hyphenated word (dehyphenation will handle later)
                result[-1] = prev + curr_stripped
            else:
                result[-1] = prev + " " + curr_stripped
        else:
            result.append(curr)

    return "\n\n".join(result)


def clean_text(text: str, word_set: set[str] | None = None) -> tuple[str, list[dict], int]:
    """Apply OCR cleanup: noise removal, pre-filters, dehyphenation, dictionary correction.

    Returns (cleaned_text, review_flags, punct_fixes) where review_flags
    lists tokens needing LLM review (unresolved hyphens, stray symbols)
    and punct_fixes is the number of punctuation normalizations applied.
    """
    # Remove noise lines (page numbers, OCR artifacts, separator patterns)
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        if not is_noise_line(line):
            cleaned_lines.append(line)
    text = "\n".join(cleaned_lines)

    # Collapse multiple blank lines (noise removal may leave gaps)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Join paragraphs falsely split at OCR page boundaries
    text = join_broken_paragraphs(text)

    # Apply high-confidence regex pre-filters (più garbles, 5AN, etc.)
    text = apply_pre_filters(text)

    # Normalize garbled punctuation (spaced quote pairs, doubled ;; ,, ::, etc.)
    text, punct_fixes = normalize_punctuation(text)

    # Dehyphenate broken words BEFORE dictionary correction —
    # otherwise spaCy splits "assicuri-azioni" into fragments and
    # symspellpy may "correct" each half to the wrong word.
    text, review_flags = dehyphenate_text(text, word_set)

    # Apply dictionary-based correction via symspellpy (NER-aware)
    text = apply_dictionary_correction(text)

    # Remove inline OCR page marker artifacts (e.g. "165 3E:", "dEE o 5E", "3E262dlE 262 5E:")
    text = re.sub(r"\s*\d+\s+[35][EI]:?\s*", " ", text)
    text = re.sub(r"\s*[dD]?[EeIi]{1,3}\s+o?\s*[35][EI]\s*", " ", text)
    text = re.sub(r"\s*[35][EI]\d+[a-z]*[EI]\s+\d+\s+[35][EI]:?\s*", " ", text)

    # Fix OCR asterisks: * replacing lost characters between word fragments
    # e.g. "Liber* tà" → "Libertà", "complot* tato" → "complottato"
    text = re.sub(r"(\w)\*\s+(\w)", r"\1\2", text)
    # e.g. "scindei*si" → "scindesi" (no space variant)
    text = re.sub(r"(\w)\*(\w)", r"\1\2", text)
    # '* or "* replacing a quote mark: e.g. '*Mano → "Mano
    text = re.sub(r"'\*\s*", '"', text)
    text = re.sub(r'"\s*\*\s*', '"', text)
    # Standalone * between words (lost text): e.g. "delle * delle" → "delle delle"
    text = re.sub(r"\s\*\s", " ", text)

    # Fix spacing around punctuation
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    text = re.sub(r"\.{4,}", "...", text)  # Normalize ellipsis

    # Collapse multiple blank lines again (inline noise removal may leave gaps)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Flag stray OCR noise symbols between words (^ replacing lost text)
    # for LLM review. Asterisks are handled above; carets may remain.
    _STRAY_SYMBOL_RE = re.compile(r"(?<=\w) ([\^]) (?=\w)")
    for m in _STRAY_SYMBOL_RE.finditer(text):
        ctx_start = max(0, m.start() - 30)
        ctx_end = min(len(text), m.end() + 30)
        review_flags.append({
            "token": m.group(1),
            "left": text[ctx_start:m.start()].split()[-1] if text[ctx_start:m.start()].split() else "",
            "right": text[m.end():ctx_end].split()[0] if text[m.end():ctx_end].split() else "",
            "offset": m.start(),
            "reason": "stray_symbol",
            "context": text[ctx_start:ctx_end],
        })

    # Flag probable f-ligature misreads: words not in dictionary that become
    # valid with fi/fl/ff ligature correction (e.g. "atterrandolo" → "afferrandolo").
    _FLIG_SUBS = [
        ("u", "fi"), ("n", "fi"), ("ri", "fi"),
        ("d", "fl"), ("tl", "fl"),
        ("tf", "ff"), ("tt", "ff"),
    ]
    _WORD_RE = re.compile(r"\b([a-zA-ZÀ-ÿ]{4,})\b")
    if word_set is None:
        word_set = _get_word_set()
    seen_flig: set[str] = set()
    for m in _WORD_RE.finditer(text):
        w = m.group(1)
        lower = w.lower()
        if lower in seen_flig or _in_word_set(lower, word_set):
            continue
        seen_flig.add(lower)
        for ocr_form, correct_form in _FLIG_SUBS:
            pos = 0
            found = False
            while not found:
                idx = lower.find(ocr_form, pos)
                if idx == -1:
                    break
                candidate = lower[:idx] + correct_form + lower[idx + len(ocr_form):]
                if _in_word_set(candidate, word_set):
                    ctx_start = max(0, m.start() - 30)
                    ctx_end = min(len(text), m.end() + 30)
                    review_flags.append({
                        "token": w,
                        "left": ocr_form,
                        "right": correct_form,
                        "offset": m.start(),
                        "reason": "f_ligature",
                        "context": text[ctx_start:ctx_end],
                        "suggestion": candidate,
                    })
                    found = True
                pos = idx + 1

    # Fix missing space after punctuation (e.g. "Trattati,ogni" → "Trattati, ogni")
    # OCR-collapsed spacing — in this text, letter+punct+letter always needs a space.
    text = re.sub(r"([a-zA-ZÀ-ÿ][,;:])([a-zA-ZÀ-ÿ])", r"\1 \2", text)

    # Flag paragraph-initial lowercase — unlikely to be intentional in this text,
    # typically a broken sentence at a page boundary or OCR noise.
    _PARA_LOWER_RE = re.compile(r"[.!?\"]\n\n([a-zà-ÿ])")
    for m in _PARA_LOWER_RE.finditer(text):
        ctx_start = max(0, m.start() - 30)
        ctx_end = min(len(text), m.end() + 30)
        review_flags.append({
            "token": m.group(1),
            "left": text[ctx_start:m.start() + 1],
            "right": text[m.start(1):ctx_end],
            "offset": m.start(1),
            "reason": "lowercase_after_break",
            "context": text[ctx_start:ctx_end],
        })

    return text.strip(), review_flags, punct_fixes


# TODO: Add Gemini 3 Pro as a fallback LLM for Italian correction when
# the Anthropic API is unavailable or timing out on specific chapters.
def llm_correct_italian(
    text: str,
    chapter_title: str,
    api_key: str,
    zingarelli_context: str = "",
) -> str:
    """Use Claude to correct remaining OCR errors in Italian text.

    If zingarelli_context is provided, it is appended to the user message
    to give the LLM period-appropriate dictionary evidence for flagged tokens.
    """
    import anthropic

    from utils import retry_api_call

    client = anthropic.Anthropic(api_key=api_key, timeout=600.0)

    max_output = 128000

    user_content = (
        f"Correct OCR errors in the following chapter ({chapter_title}). "
        f"Return only the corrected Italian text:\n\n{text}"
    )
    if zingarelli_context:
        user_content += (
            "\n\n--- REFERENCE ---\n"
            "The following tokens were flagged as potentially broken or garbled. "
            "Use the Zingarelli 1922 dictionary evidence below to inform your corrections. "
            "Tokens marked 'not found' may be proper nouns (keep as-is) or noise (remove).\n\n"
            + zingarelli_context
        )

    def _call():
        return client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=max_output,
            system=(
                "You are an expert in 19th/early 20th century Italian literature and OCR correction. "
                "You are correcting OCR artifacts in a digitized 1913 Italian book titled "
                "'Per la libertà!' by Cesare Crespi, about Count Carlo di Rudio and Felice Orsini.\n\n"
                "Rules:\n"
                "- Fix obvious OCR errors (garbled characters, wrong letters) while preserving the original Italian\n"
                "- Do NOT modernize the language or spelling — keep 1913-era Italian conventions\n"
                "- Preserve all paragraph breaks\n"
                "- Do NOT translate — output must be in Italian\n"
                "- Do NOT add or remove content — only fix OCR errors\n"
                "- Common OCR errors: 'e' for 'c', 'ii' for 'u', 'im' for 'un', 'm-' artifacts, "
                "parentheses inside words, mid-word capitals, r↔i confusion at line breaks\n"
                "- If a REFERENCE section with Zingarelli 1922 dictionary evidence is provided, "
                "use it to validate corrections for flagged tokens\n"
                "- Return ONLY the corrected text, no commentary"
            ),
            messages=[
                {"role": "user", "content": user_content}
            ],
        )

    response = retry_api_call(_call)
    result = response.content[0].text
    # Strip LLM preamble that sometimes precedes the corrected text
    result = re.sub(
        r"^(?:Here is the corrected.*?|Ecco il testo corretto.*?):\s*\n+",
        "", result, count=1, flags=re.IGNORECASE,
    )
    return result


_FLAG_REVIEW_SYSTEM = (
    "You are an expert in 19th/early 20th century Italian literature and OCR correction. "
    "You are reviewing flagged tokens from a digitized 1913 Italian book titled "
    "'Per la libertà!' by Cesare Crespi.\n\n"
    "For each flagged token, respond with ONE of:\n"
    "- FIX: original → corrected (when you can determine the right text)\n"
    "- KEEP: original (when the token is correct as-is, e.g. a real hyphenated compound or proper name)\n"
    "- UNCLEAR: original (when there isn't enough context to determine the fix)\n\n"
    "Respond with one line per token, in the same order as the input. No other commentary."
)


def _build_flag_entries(
    flags_by_chapter: dict[str, list[dict]],
    cleaned_texts: dict[str, str],
) -> tuple[str, list[tuple[str, dict]]]:
    """Build prompt entries and flat flag list from flags_by_chapter."""
    token_entries = []
    flat_flags = []
    for ch_id, ch_flags in flags_by_chapter.items():
        text = cleaned_texts.get(ch_id, "")
        for flag in ch_flags:
            token = flag.get("token", "")
            reason = flag.get("reason", "")
            ctx = flag.get("context", "")
            if not ctx and token in text:
                idx = text.find(token)
                start = max(0, idx - 60)
                end = min(len(text), idx + len(token) + 60)
                ctx = text[start:end]
            token_entries.append(
                f"[{ch_id}] ({reason}) \"{token}\" in: ...{ctx}..."
            )
            flat_flags.append((ch_id, flag))
    return "\n".join(token_entries), flat_flags


def _parse_flag_responses(result_text: str) -> dict[str, str]:
    """Parse LLM response lines into {original_token: corrected} map.

    Extracts the original token from the FIX line itself (before the →)
    rather than relying on positional alignment with the input.
    """
    fixes: dict[str, str] = {}
    lines = [l.strip() for l in result_text.strip().split("\n") if l.strip()]
    for line in lines:
        if line.startswith("FIX:"):
            parts = line[4:].split("→")
            if len(parts) == 2:
                original = parts[0].strip().strip('"')
                corrected = parts[1].strip().strip('"')
                if original and corrected and original != corrected:
                    fixes[original] = corrected
    return fixes


def _call_claude_flags(entries_text: str, api_key: str) -> str:
    """Send flag review prompt to Claude Sonnet."""
    import anthropic

    from utils import retry_api_call

    client = anthropic.Anthropic(api_key=api_key, timeout=120.0)

    def _call():
        return client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=_FLAG_REVIEW_SYSTEM,
            messages=[{"role": "user", "content": (
                "Review these flagged OCR tokens and provide corrections:\n\n"
                + entries_text
            )}],
        )

    print("  Claude reviewing...", end="", flush=True)
    response = retry_api_call(_call)
    print(f" done ({response.usage.input_tokens} in, {response.usage.output_tokens} out)")
    return response.content[0].text


def _call_gemini_flags(entries_text: str, api_key: str | None = None) -> str:
    """Send flag review prompt to Gemini Pro."""
    import os

    from google import genai
    from utils import retry_api_call

    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)

    def _call():
        return client.models.generate_content(
            model="gemini-2.5-pro",
            contents=(
                _FLAG_REVIEW_SYSTEM + "\n\n"
                "Review these flagged OCR tokens and provide corrections:\n\n"
                + entries_text
            ),
        )

    print("  Gemini reviewing...", end="", flush=True)
    response = retry_api_call(_call)
    print(" done")
    return response.text


def llm_fix_flagged_tokens(
    flags_by_chapter: dict[str, list[dict]],
    cleaned_texts: dict[str, str],
    api_key: str | None = None,
    verify: bool = False,
) -> dict[str, list[dict]]:
    """Fix flagged tokens using Claude, optionally verified by Gemini.

    When verify=True, runs both Claude and Gemini and only keeps fixes
    where both models agree on the correction.

    Returns corrections dict: {chapter_id: [{find, replace, reason}, ...]}.
    """
    entries_text, flat_flags = _build_flag_entries(flags_by_chapter, cleaned_texts)
    if not flat_flags:
        return {}

    print(f"  {len(flat_flags)} flagged tokens to review")

    # Get Claude's fixes
    claude_text = _call_claude_flags(entries_text, api_key)
    claude_fixes = _parse_flag_responses(claude_text)
    print(f"  Claude: {len(claude_fixes)} fixes proposed")

    if verify:
        # Get Gemini's fixes
        gemini_text = _call_gemini_flags(entries_text)
        gemini_fixes = _parse_flag_responses(gemini_text)
        print(f"  Gemini: {len(gemini_fixes)} fixes proposed")

        # Only keep fixes where both agree
        agreed = {}
        disagreed = []
        for token, claude_fix in claude_fixes.items():
            gemini_fix = gemini_fixes.get(token)
            if gemini_fix and gemini_fix == claude_fix:
                agreed[token] = claude_fix
            else:
                disagreed.append((token, claude_fix, gemini_fix))

        # Also check Gemini-only fixes
        for token, gemini_fix in gemini_fixes.items():
            if token not in claude_fixes:
                disagreed.append((token, None, gemini_fix))

        print(f"  Agreed: {len(agreed)}, Disagreed: {len(disagreed)}")
        if disagreed:
            print("  Disagreements:")
            for token, cf, gf in disagreed:
                print(f"    {token}: Claude={cf}, Gemini={gf}")

        final_fixes = agreed
    else:
        final_fixes = claude_fixes

    # Build corrections dict keyed by chapter
    corrections: dict[str, list[dict]] = {}
    for ch_id, flag in flat_flags:
        token = flag.get("token", "")
        if token in final_fixes:
            corrections.setdefault(ch_id, []).append({
                "find": token,
                "replace": final_fixes[token],
                "reason": f"llm_flag_fix:{flag.get('reason', '')}",
            })

    total = sum(len(v) for v in corrections.values())
    print(f"  Final: {total} corrections to apply")
    return corrections


def apply_corrections(
    text: str,
    chapter_id: str,
    corrections: dict[str, list[dict]],
    review_flags: list[dict],
) -> tuple[str, list[dict], int]:
    """Apply saved corrections to cleaned text and suppress resolved flags.

    Returns (corrected_text, remaining_flags, applied_count).
    """
    chapter_corrections = corrections.get(chapter_id, [])
    if not chapter_corrections:
        return text, review_flags, 0

    applied = 0
    suppressed_tokens: set[str] = set()

    for entry in chapter_corrections:
        find = entry["find"]
        replace = entry["replace"]

        if find not in text:
            continue

        if replace == ":override":
            # Suppress the flag but leave text unchanged
            suppressed_tokens.add(find)
            applied += 1
        else:
            text = text.replace(find, replace, 1)
            suppressed_tokens.add(find)
            applied += 1

    # Remove flags whose token or context matches a correction
    if suppressed_tokens:
        remaining = []
        for flag in review_flags:
            token = flag.get("token", "")
            context = flag.get("context", "")
            if any(t in token or t in context for t in suppressed_tokens):
                continue
            remaining.append(flag)
        review_flags = remaining

    return text, review_flags, applied


def extract_corrections_from_diff(
    original: str,
    corrected: str,
    chapter_id: str,
    context_chars: int = 40,
) -> list[dict]:
    """Diff original and LLM-corrected text to extract individual corrections.

    Each correction captures enough surrounding context to be unique.
    Returns a list of correction entries for corrections.json.
    """
    sm = difflib.SequenceMatcher(None, original, corrected, autojunk=False)
    corrections = []

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue

        orig_snippet = original[i1:i2]
        new_snippet = corrected[j1:j2]

        # Skip whitespace-only changes
        if orig_snippet.strip() == new_snippet.strip():
            continue

        # Build find string with enough context to be unique
        ctx_start = max(0, i1 - context_chars)
        ctx_end = min(len(original), i2 + context_chars)
        find_with_ctx = original[ctx_start:ctx_end]

        # Build corresponding replacement (same context, different core)
        replace_with_ctx = original[ctx_start:i1] + new_snippet + original[i2:ctx_end]

        corrections.append({
            "find": find_with_ctx,
            "replace": replace_with_ctx,
            "reason": "llm_correction",
            "source": "llm",
        })

    return corrections


def cleanup(data_dir: Path, output_dir: Path, use_llm: bool = False, api_key: str | None = None, chapter: str | None = None) -> None:
    """Clean reconciled text and produce final Italian markdown.

    If chapter is set (e.g. 'p2_ch21'), only that chapter gets the LLM pass;
    all others apply cached corrections only.
    """
    chapters_path = data_dir / "reconciled_chapters.json"
    chapters = json.loads(chapters_path.read_text(encoding="utf-8"))

    # Load page provenance if available (from 3-way reconciliation)
    chapter_pages_path = data_dir / "chapter_pages.json"
    chapter_pages = {}
    if chapter_pages_path.exists():
        chapter_pages = json.loads(chapter_pages_path.read_text(encoding="utf-8"))
        print(f"  Page provenance loaded for {len(chapter_pages)} chapters")

    # Load durable corrections file (persists LLM fixes and manual overrides)
    corrections_path = data_dir / "corrections.json"
    corrections: dict[str, list[dict]] = {}
    if corrections_path.exists():
        corrections = json.loads(corrections_path.read_text(encoding="utf-8"))
        total_entries = sum(len(v) for v in corrections.values())
        print(f"  Corrections loaded: {total_entries} entries from {corrections_path.name}")

    output_dir.mkdir(parents=True, exist_ok=True)

    if use_llm and not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("  Warning: No API key provided, skipping LLM correction")
            use_llm = False

    # Pre-load the word set once for all chapters
    word_set = _get_word_set()

    # Sort chapters: prefazione first, then p1_ch01..p1_ch24, then p2_ch01..p2_ch33
    def chapter_sort_key(ch):
        if ch["id"] == "prefazione":
            return (0, 0, 0)
        parts = ch["id"].split("_")
        part_num = int(parts[0][1:]) if parts[0].startswith("p") else 0
        ch_num = int(parts[1][2:]) if len(parts) > 1 else 0
        return (1, part_num, ch_num)

    chapters.sort(key=chapter_sort_key)

    # Build markdown output
    md_lines = [
        "# Per la Libertà!",
        "",
        "*Dalle mie conversazioni col Conte Carlo di Rudio, complice di Felice Orsini*",
        "",
        "**Cesare Crespi** (1913)",
        "",
        "---",
        "",
    ]

    current_part = 0
    total = len(chapters)
    all_flags: dict[str, list[dict]] = {}
    dehyphen_fixed = 0
    review_flagged = 0
    total_punct_fixes = 0
    total_corrections_applied = 0
    new_corrections: dict[str, list[dict]] = {}

    for i, ch in enumerate(chapters):
        text, flags, punct_fixes = clean_text(ch["text"], word_set)
        total_punct_fixes += punct_fixes

        # Apply durable corrections (LLM fixes from prior runs + manual overrides)
        text, flags, n_applied = apply_corrections(text, ch["id"], corrections, flags)
        total_corrections_applied += n_applied

        if flags:
            all_flags[ch["id"]] = flags
            review_flagged += len(flags)

        if use_llm:
            bar_width = 30
            filled = int(bar_width * (i / total))
            bar = "█" * filled + "░" * (bar_width - filled)
            # Determine if this chapter should get the LLM pass
            if chapter is not None:
                run_llm = ch["id"] == chapter
            else:
                run_llm = not corrections.get(ch["id"])
            if not run_llm:
                print(f"\r  [{bar}] {i+1}/{total}  {ch['title']:<35s} (cached)", end="", flush=True)
            else:
                print(f"\r  [{bar}] {i+1}/{total}  {ch['title']:<35s}", end="", flush=True)
                try:
                    # Build Zingarelli context for this chapter's flagged tokens
                    zingarelli_ctx = ""
                    if flags:
                        from adjudicate import zingarelli_context_for_flags
                        zingarelli_ctx = zingarelli_context_for_flags(flags)
                    pre_llm_text = text
                    text = llm_correct_italian(text, ch["title"], api_key, zingarelli_ctx)
                    # Extract individual corrections from the LLM diff
                    ch_corrections = extract_corrections_from_diff(
                        pre_llm_text, text, ch["id"]
                    )
                    if ch_corrections:
                        new_corrections[ch["id"]] = ch_corrections
                    time.sleep(1)  # Rate limiting
                except Exception as e:
                    print(f"\n    LLM error on {ch['id']}, using regex-cleaned text: {e}")

        # Add part headers
        if ch["part"] != current_part:
            if ch["part"] == 1:
                md_lines.extend(["## Parte Prima", ""])
            elif ch["part"] == 2:
                md_lines.extend(["---", "", "## Parte Seconda", ""])
            current_part = ch["part"]

        # Add chapter header
        if ch["id"] == "prefazione":
            md_lines.extend(["## Prefazione", ""])
        else:
            # Normalize chapter title
            ch_num = ch["id"].split("_ch")[1] if "_ch" in ch["id"] else ""
            md_lines.extend([f"### {ch['title']}", ""])

        # Insert page provenance marker if available
        pages = chapter_pages.get(ch["id"])
        if pages:
            md_lines.append(f"<!-- pages:{pages[0]}-{pages[-1]} -->")
            md_lines.append("")

        md_lines.append(text)
        md_lines.extend(["", ""])

        if not use_llm:
            print(f"  Cleaned: {ch['id']} ({len(text):,} chars)")

    if use_llm:
        bar = "█" * bar_width
        print(f"\r  [{bar}] {total}/{total}  Done!{' ' * 30}")

    output_path = output_dir / "italian_clean.md"
    output_path.write_text("\n".join(md_lines), encoding="utf-8")

    # Write sidecar file with unresolved hyphenated tokens for LLM adjudication
    sidecar_path = data_dir / "review_flags.json"
    if total_punct_fixes:
        print(f"  Punctuation: {total_punct_fixes} fixes (garbled quotes, doubled punctuation, stray guillemets)")

    if total_corrections_applied:
        print(f"  Corrections: {total_corrections_applied} applied from {corrections_path.name}")

    # Merge new LLM corrections into the durable corrections file
    if new_corrections:
        from utils import atomic_write_json
        for ch_id, ch_corrs in new_corrections.items():
            existing = corrections.get(ch_id, [])
            # Avoid duplicates: skip corrections whose find string already exists
            existing_finds = {e["find"] for e in existing}
            for c in ch_corrs:
                if c["find"] not in existing_finds:
                    existing.append(c)
            corrections[ch_id] = existing
        atomic_write_json(corrections_path, corrections)
        new_count = sum(len(v) for v in new_corrections.values())
        print(f"  New LLM corrections: {new_count} saved → {corrections_path.name}")

    if all_flags:
        from utils import atomic_write_json
        atomic_write_json(sidecar_path, all_flags)
        print(f"  Review flags: {review_flagged} tokens flagged for LLM review → {sidecar_path.name}")
    elif sidecar_path.exists():
        sidecar_path.unlink()

    print(f"\n  Output: {output_path}")
    print(f"  Total chapters: {len(chapters)}")


def reconcile_flags(data_dir: Path, output_dir: Path) -> None:
    """Compare review_flags.json against the final output and write only surviving flags.

    Preserves review_flags.json (pre-LLM) intact; writes review_flags_remaining.json
    with only the flags whose context still appears in italian_clean.md.
    """
    flags_path = data_dir / "review_flags.json"
    output_path = output_dir / "italian_clean.md"

    if not flags_path.exists() or not output_path.exists():
        print("  reconcile_flags: missing review_flags.json or italian_clean.md, skipping")
        return

    flags = json.loads(flags_path.read_text(encoding="utf-8"))
    output_text = output_path.read_text(encoding="utf-8")

    remaining: dict[str, list[dict]] = {}
    total_original = 0
    total_remaining = 0

    for ch_id, ch_flags in flags.items():
        for f in ch_flags:
            total_original += 1
            context = f.get("context", "").strip()
            token = f.get("token", "")
            search = context if context else token
            if search and search in output_text:
                remaining.setdefault(ch_id, []).append(f)
                total_remaining += 1

    from utils import atomic_write_json

    remaining_path = data_dir / "review_flags_remaining.json"
    atomic_write_json(remaining_path, remaining)

    resolved = total_original - total_remaining
    print(f"  Flag reconciliation: {total_original} original → {total_remaining} remaining ({resolved} resolved by LLM)")
    print(f"  Original flags preserved: {flags_path.name}")
    print(f"  Remaining flags written: {remaining_path.name}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true", help="Use LLM for Italian correction")
    parser.add_argument("--api-key", help="Anthropic API key")
    args = parser.parse_args()

    base = Path(__file__).parent
    cleanup(base / "data", base / "output", use_llm=args.llm, api_key=args.api_key)
