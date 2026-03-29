"""Step 3: Clean OCR artifacts and optionally use LLM for Italian text correction."""

import json
import os
import re
import time
from pathlib import Path


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


def clean_text(text: str) -> str:
    """Apply OCR cleanup: noise removal, pre-filters, dictionary correction."""
    # Remove noise lines
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        if not is_noise_line(line):
            cleaned_lines.append(line)
    text = "\n".join(cleaned_lines)

    # Apply high-confidence regex pre-filters (più garbles, 5AN, etc.)
    text = apply_pre_filters(text)

    # Apply dictionary-based correction via symspellpy (NER-aware)
    text = apply_dictionary_correction(text)

    # Remove inline OCR page marker artifacts (e.g. "165 3E:", "dEE o 5E", "3E262dlE 262 5E:")
    text = re.sub(r"\s*\d+\s+[35][EI]:?\s*", " ", text)
    text = re.sub(r"\s*[dD]?[EeIi]{1,3}\s+o?\s*[35][EI]\s*", " ", text)
    text = re.sub(r"\s*[35][EI]\d+[a-z]*[EI]\s+\d+\s+[35][EI]:?\s*", " ", text)

    # Fix spacing around punctuation
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    text = re.sub(r"\.{4,}", "...", text)  # Normalize ellipsis

    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def llm_correct_italian(text: str, chapter_title: str, api_key: str) -> str:
    """Use Claude to correct remaining OCR errors in Italian text."""
    import anthropic

    from utils import retry_api_call

    client = anthropic.Anthropic(api_key=api_key, timeout=300.0)

    max_output = 128000

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
                "parentheses inside words, mid-word capitals\n"
                "- Return ONLY the corrected text, no commentary"
            ),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Correct OCR errors in the following chapter ({chapter_title}). "
                        f"Return only the corrected Italian text:\n\n{text}"
                    ),
                }
            ],
        )

    response = retry_api_call(_call)
    return response.content[0].text


def cleanup(data_dir: Path, output_dir: Path, use_llm: bool = False, api_key: str | None = None) -> None:
    """Clean reconciled text and produce final Italian markdown."""
    chapters_path = data_dir / "reconciled_chapters.json"
    chapters = json.loads(chapters_path.read_text(encoding="utf-8"))

    # Load page provenance if available (from 3-way reconciliation)
    chapter_pages_path = data_dir / "chapter_pages.json"
    chapter_pages = {}
    if chapter_pages_path.exists():
        chapter_pages = json.loads(chapter_pages_path.read_text(encoding="utf-8"))
        print(f"  Page provenance loaded for {len(chapter_pages)} chapters")

    output_dir.mkdir(parents=True, exist_ok=True)

    if use_llm and not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("  Warning: No API key provided, skipping LLM correction")
            use_llm = False

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

    for i, ch in enumerate(chapters):
        text = clean_text(ch["text"])

        if use_llm:
            bar_width = 30
            filled = int(bar_width * (i / total))
            bar = "█" * filled + "░" * (bar_width - filled)
            print(f"\r  [{bar}] {i+1}/{total}  {ch['title']:<35s}", end="", flush=True)
            try:
                text = llm_correct_italian(text, ch["title"], api_key)
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
    print(f"\n  Output: {output_path}")
    print(f"  Total chapters: {len(chapters)}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true", help="Use LLM for Italian correction")
    parser.add_argument("--api-key", help="Anthropic API key")
    args = parser.parse_args()

    base = Path(__file__).parent
    cleanup(base / "data", base / "output", use_llm=args.llm, api_key=args.api_key)
