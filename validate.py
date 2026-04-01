"""Step 5: Validate cleaned Italian text before translation."""

import json
import re
from pathlib import Path


def check_chapter_count(text: str) -> dict:
    """Verify expected chapter structure: prefazione + 24 Part 1 + 33 Part 2 = 58."""
    h2_count = len(re.findall(r"^## ", text, re.MULTILINE))
    h3_count = len(re.findall(r"^### ", text, re.MULTILINE))

    # Expected: ## Prefazione, ## Parte Prima, ## Parte Seconda = 3 h2
    # Plus ### Capitolo ... × 57 = 57 h3
    issues = []
    if h2_count < 3:
        issues.append(f"Expected at least 3 ## headers (Prefazione, Parte Prima, Parte Seconda), found {h2_count}")
    if h3_count != 57:
        issues.append(f"Expected 57 ### chapter headers (24 Part 1 + 33 Part 2), found {h3_count}")

    return {
        "name": "chapter_count",
        "passed": len(issues) == 0,
        "h2_count": h2_count,
        "h3_count": h3_count,
        "issues": issues,
    }


def check_word_count_preservation(cleaned_text: str, reconciled_path: Path) -> dict:
    """Check that cleanup didn't lose excessive content.

    The reconciled text includes OCR noise lines (page numbers, decorations)
    that cleanup intentionally removes, so some word count reduction is expected.
    This check flags if cleaned text is suspiciously small relative to reconciled
    (< 60% would indicate data loss beyond normal noise removal).
    """
    chapters = json.loads(reconciled_path.read_text(encoding="utf-8"))
    reconciled_words = sum(len(ch["text"].split()) for ch in chapters)

    # Strip markdown headers and page markers for fair comparison
    clean = re.sub(r"^#+\s.*$", "", cleaned_text, flags=re.MULTILINE)
    clean = re.sub(r"<!--\s*page:\d+\s*-->", "", clean)
    clean = re.sub(r"^---$", "", clean, flags=re.MULTILINE)
    clean = re.sub(r"^\*.*\*$", "", clean, flags=re.MULTILINE)  # metadata lines
    cleaned_words = len(clean.split())

    if reconciled_words == 0:
        return {"name": "word_count_preservation", "passed": False,
                "issues": ["Reconciled text has 0 words"]}

    ratio = cleaned_words / reconciled_words
    passed = ratio >= 0.60  # Cleanup removes ~30% noise; below 60% indicates data loss

    issues = []
    if not passed:
        issues.append(
            f"Cleaned text is only {ratio:.0%} of reconciled ({cleaned_words:,} vs "
            f"{reconciled_words:,} words) — possible data loss"
        )

    return {
        "name": "word_count_preservation",
        "passed": passed,
        "reconciled_words": reconciled_words,
        "cleaned_words": cleaned_words,
        "retention_pct": round(ratio * 100, 1),
        "issues": issues,
    }


def check_no_empty_chapters(text: str) -> dict:
    """No chapters should have empty or near-empty content."""
    issues = []
    # Split on headers
    sections = re.split(r"^(#{2,3}\s.+)$", text, flags=re.MULTILINE)

    i = 1  # Skip content before first header
    while i < len(sections) - 1:
        header = sections[i].strip()
        content = sections[i + 1].strip() if i + 1 < len(sections) else ""

        # Skip structural headers (Parte Prima/Seconda)
        if any(s in header for s in ("Parte Prima", "Parte Seconda")):
            i += 2
            continue

        # Check if chapter content is essentially empty
        # Remove page markers and whitespace for counting
        clean_content = re.sub(r"<!--\s*page:\d+\s*-->", "", content).strip()
        if header.startswith("###") and len(clean_content) < 50:
            issues.append(f"Near-empty chapter: {header} ({len(clean_content)} chars)")

        i += 2

    return {
        "name": "no_empty_chapters",
        "passed": len(issues) == 0,
        "issues": issues,
    }


def check_quote_balance(text: str) -> dict:
    """Check for balanced quotation marks."""
    issues = []

    # Italian guillemets
    left_g = text.count("\u00ab")   # «
    right_g = text.count("\u00bb")  # »
    if left_g != right_g:
        issues.append(f"Guillemet imbalance: {left_g} « vs {right_g} »")

    # Smart double quotes
    left_dq = text.count("\u201c")  # "
    right_dq = text.count("\u201d")  # "
    if left_dq != right_dq:
        issues.append(f"Smart double quote imbalance: {left_dq} \u201c vs {right_dq} \u201d")

    return {
        "name": "quote_balance",
        "passed": len(issues) == 0,
        "issues": issues,
    }


def check_italian_char_coverage(text: str) -> dict:
    """Verify text is predominantly Italian-alphabet characters.

    Flag if > 0.5% of non-whitespace characters are outside the expected
    Italian character set (letters, accented vowels, standard punctuation).
    """
    # Italian alphabet + accented vowels + standard punctuation + digits
    italian_pattern = re.compile(
        r"[a-zA-ZàèìòùéÀÈÌÒÙÉ"
        r"0-9"
        r"\s"
        r".,;:!?\-—–''\u2019\u2018\"«»\u201c\u201d"
        r"()\[\]/"
        r"\u2026"  # ellipsis
        r"]"
    )

    non_ws_chars = [c for c in text if not c.isspace()]
    if not non_ws_chars:
        return {"name": "italian_char_coverage", "passed": True, "issues": []}

    foreign_chars = [c for c in non_ws_chars if not italian_pattern.match(c)]
    ratio = len(foreign_chars) / len(non_ws_chars)

    issues = []
    if ratio > 0.005:
        # Sample the foreign chars for the report
        sample = set(foreign_chars[:50])
        issues.append(
            f"{ratio:.2%} non-Italian chars ({len(foreign_chars):,} of "
            f"{len(non_ws_chars):,}). Sample: {sorted(sample)}"
        )

    return {
        "name": "italian_char_coverage",
        "passed": ratio <= 0.005,
        "foreign_char_ratio": round(ratio * 100, 3),
        "issues": issues,
    }


def check_no_ascii_remnants(text: str) -> dict:
    """Check for remaining OCR artifacts that should have been cleaned."""
    issues = []

    # Page marker artifacts (e.g., "165 3E:", "dEE o 5E")
    page_markers = re.findall(r"\d+\s+[35][EI]:?", text)
    if page_markers:
        issues.append(f"{len(page_markers)} page marker artifacts remain (e.g., {page_markers[:3]})")

    # Runs of uppercase + digits that look like OCR noise — but only if they
    # contain digits (pure all-caps words like ANGELES, POPOLO are legitimate
    # Italian text, especially in titles and emphatic passages).
    noise_runs = re.findall(r"\b(?=[A-Z\d]*\d)[A-Z\d]{5,}\b", text)
    roman = re.compile(r"^[IVXLCDM]+$")
    noise_runs = [r for r in noise_runs if not roman.match(r)]
    if noise_runs:
        issues.append(f"{len(noise_runs)} potential OCR noise runs (e.g., {noise_runs[:3]})")

    return {
        "name": "no_ascii_remnants",
        "passed": len(issues) == 0,
        "issues": issues,
    }


def check_word_quality(text: str, data_dir: Path) -> dict:
    """Per-word OCR quality scan: dictionary lookup + pattern-based garble detection.

    Flags:
    - Words not in Italian dictionary (potential OCR garble)
    - Mid-word noise: digits, parentheses, brackets, carets, mixed case
    - Impossible Italian consonant clusters (4+ consecutive consonants)
    - English words (possible LLM instruction leaks)
    - Orphan single letters that suggest broken words

    Returns check dict with per-chapter breakdown of flagged words.
    """
    from cleanup import _get_ner_nlp, _get_word_set, _strip_accents

    word_set = _get_word_set()
    nlp = _get_ner_nlp()

    # Build a set of known entities from the full text via spaCy NER.
    # These are proper nouns, place names, etc. that won't be in the
    # frequency dictionary but are legitimate.
    known_entities: set[str] = set()
    # Process in chunks (spaCy max_length)
    for chunk_start in range(0, len(text), 500_000):
        doc = nlp(text[chunk_start:chunk_start + 500_000])
        for ent in doc.ents:
            for token in ent.text.split():
                known_entities.add(token.lower().strip(".,;:!?\"'""''«»—-"))

    # Common English words that would indicate LLM instruction leaks
    ENGLISH_MARKERS = {
        "the", "and", "this", "that", "with", "from", "have", "will",
        "correct", "errors", "chapter", "text", "following", "here",
        "carefully", "preserve", "original", "artifacts",
    }

    # Common Italian function words to skip (too short for dictionary, always valid)
    SKIP_WORDS = {
        "a", "e", "i", "o", "è", "il", "la", "le", "lo", "li", "un",
        "di", "da", "in", "su", "ma", "se", "no", "sì", "ci", "vi",
        "ne", "al", "ai", "ha", "ho", "fu", "fa", "va", "oh", "ah",
    }

    # Pattern: 4+ consecutive consonants (very rare in Italian)
    CONSONANT_CLUSTER = re.compile(r"[bcdfghjklmnpqrstvwxyz]{4,}", re.IGNORECASE)

    # Pattern: mid-word noise
    MID_NOISE = re.compile(r"[a-zA-Z][(\)\[\]{}^\\|<>0-9][a-zA-Z]")

    # Pattern: mixed case inside a word (not at start) e.g. "comprMidi"
    MID_CAPS = re.compile(r"[a-z][A-Z][a-z]")

    # Split text into chapters
    chapter_sections = re.split(r"^(#{2,3}\s.+)$", text, flags=re.MULTILINE)

    WORD_RE = re.compile(r"\b([a-zA-ZÀ-ÿ]+(?:['''][a-zA-ZÀ-ÿ]+)?)\b")

    all_flags: list[dict] = []
    chapter_name = "Header"

    for section in chapter_sections:
        if section.startswith("#"):
            chapter_name = section.strip("# \n")
            continue

        # Skip page markers and metadata
        content = re.sub(r"<!--.*?-->", "", section)
        if not content.strip():
            continue

        for line_offset, line in enumerate(content.split("\n")):
            if not line.strip():
                continue

            for m in WORD_RE.finditer(line):
                word = m.group(1)
                # Strip apostrophe-attached clitics for lookup
                core = word.split("'")[0] if "'" in word else word.split("\u2019")[0] if "\u2019" in word else word
                lower = core.lower()

                if lower in SKIP_WORDS or len(core) <= 1:
                    continue

                reasons = []

                # Check: mid-word noise characters
                if MID_NOISE.search(word):
                    reasons.append("mid-word noise")

                # Check: mid-word capitals (e.g. "comprMidi", "BeUxmo")
                if MID_CAPS.search(core):
                    reasons.append("mid-word capitals")

                # Check: impossible consonant cluster (skip NER-recognized entities)
                if lower not in known_entities:
                    cluster_match = CONSONANT_CLUSTER.search(_strip_accents(lower))
                    if cluster_match:
                        reasons.append(f"consonant cluster '{cluster_match.group()}'")

                # Check: English marker word
                if lower in ENGLISH_MARKERS:
                    reasons.append("English word")

                # Check: not in Italian dictionary (only for words ≥ 4 chars)
                # Skip NER-recognized entities (proper nouns, place names)
                if len(core) >= 4 and not reasons and lower not in known_entities:
                    in_dict = (
                        lower in word_set
                        or _strip_accents(lower) in word_set
                        or (core[0].isupper() and lower in word_set)
                    )
                    if not in_dict:
                        reasons.append("not in dictionary")

                if reasons:
                    # Get surrounding context
                    ctx_start = max(0, m.start() - 30)
                    ctx_end = min(len(line), m.end() + 30)
                    all_flags.append({
                        "word": word,
                        "chapter": chapter_name,
                        "reasons": reasons,
                        "context": line[ctx_start:ctx_end].strip(),
                    })

    # Summarize by chapter
    by_chapter: dict[str, list[dict]] = {}
    for flag in all_flags:
        ch = flag["chapter"]
        if ch not in by_chapter:
            by_chapter[ch] = []
        by_chapter[ch].append(flag)

    # Deduplicate by word per chapter (same word flagged multiple times)
    total_unique = 0
    chapter_summary = []
    for ch_name, flags in sorted(by_chapter.items()):
        seen_words: set[str] = set()
        unique_flags = []
        for f in flags:
            if f["word"].lower() not in seen_words:
                seen_words.add(f["word"].lower())
                unique_flags.append(f)
        by_chapter[ch_name] = unique_flags
        total_unique += len(unique_flags)
        chapter_summary.append(f"{ch_name}: {len(unique_flags)} flagged")

    # Classify severity — consonant clusters in capitalized words are likely
    # proper nouns (Radetzky, Sylva) so only flag them as high-severity if
    # the word is lowercase.
    high_severity = [f for f in all_flags if any(
        r in ("mid-word noise", "mid-word capitals", "English word")
        or (r.startswith("consonant cluster") and f["word"][0].islower())
        for r in f["reasons"]
    )]

    issues = []
    if high_severity:
        issues.append(
            f"{len(high_severity)} high-severity flags (noise/garble patterns)"
        )
    if total_unique > 200:
        issues.append(
            f"{total_unique} total unique flagged words across {len(by_chapter)} chapters"
        )

    return {
        "name": "word_quality",
        "passed": len(high_severity) == 0,
        "total_flagged": total_unique,
        "high_severity": len(high_severity),
        "by_chapter": {ch: [{"word": f["word"], "reasons": f["reasons"],
                             "context": f["context"]} for f in flags]
                       for ch, flags in by_chapter.items()},
        "chapter_summary": chapter_summary,
        "issues": issues,
    }


def validate(output_dir: Path, data_dir: Path) -> dict:
    """Run all validation checks on cleaned Italian markdown.

    Returns report dict and prints summary.
    """
    italian_path = output_dir / "italian_clean.md"
    if not italian_path.exists():
        print("  Error: italian_clean.md not found")
        return {"overall": "error", "checks": [], "issues": ["italian_clean.md not found"]}

    text = italian_path.read_text(encoding="utf-8")
    reconciled_path = data_dir / "reconciled_chapters.json"

    checks = [
        check_chapter_count(text),
        check_no_empty_chapters(text),
        check_quote_balance(text),
        check_italian_char_coverage(text),
        check_no_ascii_remnants(text),
        check_word_quality(text, data_dir),
    ]

    # Word count check requires reconciled data
    if reconciled_path.exists():
        checks.append(check_word_count_preservation(text, reconciled_path))
    else:
        checks.append({
            "name": "word_count_preservation",
            "passed": False,
            "issues": ["reconciled_chapters.json not found — cannot compare"],
        })

    overall = "pass" if all(c["passed"] for c in checks) else "fail"

    report = {
        "overall": overall,
        "checks": checks,
    }

    # Print summary
    for check in checks:
        status = "\u2713" if check["passed"] else "\u2717"
        print(f"  {status} {check['name']}")
        for issue in check.get("issues", []):
            print(f"      {issue}")

        # Extra detail for word_quality check
        if check["name"] == "word_quality" and check.get("by_chapter"):
            by_ch = check["by_chapter"]
            # Show chapters with high-severity flags
            for ch_name, flags in sorted(by_ch.items()):
                severe = [f for f in flags if any(
                    r != "not in dictionary" for r in f["reasons"]
                )]
                if severe:
                    print(f"      {ch_name}:")
                    for f in severe[:5]:
                        print(f"        {f['word']:20s} {', '.join(f['reasons']):30s} ...{f['context'][:60]}")
                    if len(severe) > 5:
                        print(f"        ... and {len(severe) - 5} more")

    print(f"\n  Overall: {overall.upper()}")

    # Write report
    report_path = data_dir / "validation_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  Report: {report_path}")

    return report


if __name__ == "__main__":
    base = Path(__file__).parent
    validate(base / "output", base / "data")
