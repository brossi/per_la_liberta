"""Multi-witness translation: Draft → Evaluate → Synthesize.

Generates independent translations from multiple models, evaluates each on
literary quality dimensions (inspired by LiTransProQA, EMNLP 2025), then
synthesises the best result using Claude Code Opus 4.6 via `claude -p`.

Usage:
    uv run python pipeline.py --step translate --multi-model
    uv run python pipeline.py --step translate --multi-model --draft-models claude,gemini,gpt
    uv run python pipeline.py --step translate --multi-model --chapter p1_ch01
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from providers import (
    TranslationProvider,
    TranslationResult,
    create_provider,
)
from translate import SYSTEM_PROMPT, assemble_translation, parse_italian_markdown


# ── Evaluation ───────────────────────────────────────────────────────

EVALUATION_DIMENSIONS = [
    {
        "name": "Tone & Authorial Voice",
        "weight": 0.25,
        "questions": [
            "Does the translation preserve the early 20th century literary register of the original?",
            "Does the translation maintain Crespi's conversational narrative voice?",
            "Are formal/informal shifts in the original reflected appropriately in English?",
        ],
    },
    {
        "name": "Cultural Context & Adaptation",
        "weight": 0.20,
        "questions": [
            "Are Risorgimento-era political terms and institutions rendered with period-appropriate English equivalents?",
            "Are Italian cultural references preserved or glossed appropriately rather than silently modernised?",
        ],
    },
    {
        "name": "Accuracy & Faithfulness",
        "weight": 0.20,
        "questions": [
            "Does the translation convey the same meaning as the Italian source without omissions or additions?",
            "Are proper nouns, place names, and historical references preserved in their original Italian form?",
        ],
    },
    {
        "name": "Literary Quality",
        "weight": 0.15,
        "questions": [
            "Does the English prose read naturally and flow well as literature, not as a mechanical translation?",
            "Are figurative expressions and imagery rendered effectively in English?",
        ],
    },
    {
        "name": "Grammar & Fluency",
        "weight": 0.10,
        "questions": [
            "Is the English grammatically correct and free of awkward constructions?",
            "Is the translation readable and clear without requiring re-reading?",
        ],
    },
    {
        "name": "Consistency",
        "weight": 0.10,
        "questions": [
            "Are recurring terms and character names translated consistently throughout the passage?",
            "Does the translation maintain a coherent style from paragraph to paragraph?",
        ],
    },
]

EVALUATION_PROMPT = """\
You are evaluating an English translation of a passage from a 1913 Italian book \
titled 'Per la Libertà!' by Cesare Crespi. The book documents conversations with \
Count Carlo di Rudio about Italian unification and the Orsini conspiracy.

Below you will find the Italian source text and one English translation to evaluate.

## Italian Source
{italian_text}

## English Translation (by {model_name})
{translation_text}

## Evaluation Task

Score this translation on each dimension below. For each question, answer:
- "yes" (1.0) if the translation fully satisfies the criterion
- "partial" (0.5) if it partially satisfies or is inconsistent
- "no" (0.0) if it fails the criterion

Respond ONLY with valid JSON in exactly this format:
{{
  "dimensions": [
    {{
      "name": "<dimension name>",
      "questions": [
        {{"question": "<question text>", "score": <1.0|0.5|0.0>, "note": "<brief rationale>"}}
      ],
      "strengths": "<what this translation does well on this dimension>",
      "weaknesses": "<where it falls short>"
    }}
  ]
}}

Dimensions to evaluate:
{dimensions_block}
"""


def _build_dimensions_block() -> str:
    """Format the evaluation dimensions for the prompt."""
    lines = []
    for dim in EVALUATION_DIMENSIONS:
        lines.append(f"\n### {dim['name']} (weight: {dim['weight']})")
        for q in dim["questions"]:
            lines.append(f"- {q}")
    return "\n".join(lines)


def _compute_weighted_score(eval_result: dict) -> float:
    """Compute the overall weighted score from an evaluation JSON."""
    weight_map = {d["name"]: d["weight"] for d in EVALUATION_DIMENSIONS}
    total = 0.0
    for dim in eval_result.get("dimensions", []):
        weight = weight_map.get(dim["name"], 0.0)
        questions = dim.get("questions", [])
        if questions:
            dim_score = sum(q.get("score", 0.0) for q in questions) / len(questions)
        else:
            dim_score = 0.0
        total += weight * dim_score
    return total


# ── Synthesis ────────────────────────────────────────────────────────

SYNTHESIS_PROMPT_TEMPLATE = """\
You are synthesising the best possible English translation of an Italian chapter \
from a 1913 book titled 'Per la Libertà!' by Cesare Crespi.

Read the synthesis brief at {brief_path} — it contains ALL materials in one file: \
the Italian source, draft translations with evaluation scores, dictionary context, \
narrative reference, and (if applicable) the previous chapter's translation.

Your task:
1. Identify the strongest draft based on evaluation scores
2. Start from that draft and incorporate superior phrasings from other drafts \
WHERE evaluation evidence supports it
3. Do NOT average styles or stitch together incompatible registers
4. Maintain the early 20th century literary tone throughout
5. Consult the Edgren dictionary section for period-appropriate word choices — \
prefer 1901 English renderings over modern equivalents where they differ
6. Cross-check characters, historical references, dates, and events against \
the narrative context section. If a draft introduces details not present in the \
Italian source, omit them. Use the terminology conventions specified (e.g. keep \
"Risorgimento" in italics, keep prison names in their original form).
{prev_chapter_instruction}

Write ONLY the final English translation to {output_path}. No commentary, \
no annotations, no explanation — just the translated text."""

PROVENANCE_PROMPT_TEMPLATE = """\
You synthesised an English translation from multiple drafts. Now document what you did.

Read the synthesis brief at {brief_path} — it contains the drafts, evaluation \
scores, and dictionary context. Then read the final translation at {output_path}.

Write a provenance log to {provenance_path} as a JSON file with this structure:
{{
  "primary_draft": "<name of the draft used as the base>",
  "incorporations": [
    {{
      "paragraph": <1-indexed paragraph number in the final translation>,
      "from_draft": "<name of the other draft>",
      "original": "<phrase from the primary draft that was replaced>",
      "replacement": "<phrase used in the final translation>",
      "reason": "<why this phrasing is superior>"
    }}
  ],
  "edgren_influences": [
    {{
      "italian_word": "<the Italian word looked up>",
      "edgren_definition": "<the relevant Edgren entry or sense>",
      "english_choice": "<the English word/phrase used in the final translation>",
      "paragraph": <1-indexed paragraph number>,
      "note": "<how the dictionary informed this choice vs a modern default>"
    }}
  ]
}}

Compare the final translation against each draft to identify specific differences. \
For each difference, determine whether it came from another draft (incorporation) \
or from Edgren dictionary influence. If the final translation matches the primary \
draft exactly with no changes, set both lists to empty.

Be honest — only log genuine influences, not post-hoc justifications."""


def _assemble_synthesis_brief(
    materials_dir: Path,
    prev_chapter_text: str | None = None,
) -> Path:
    """Assemble all synthesis materials into a single brief file.

    This eliminates multi-turn file reads — Opus reads one file, thinks, writes.
    Returns the path to the assembled brief.
    """
    sections = []

    # Italian source
    src_path = materials_dir / "italian_source.txt"
    if src_path.exists():
        sections.append("=" * 60)
        sections.append("ITALIAN SOURCE TEXT")
        sections.append("=" * 60)
        sections.append(src_path.read_text(encoding="utf-8"))

    # Drafts with their evaluation scores
    for p in sorted(materials_dir.glob("draft_*.md")):
        draft_name = p.stem  # e.g. draft_claude__sonnet
        sections.append("")
        sections.append("=" * 60)
        sections.append(f"TRANSLATION DRAFT: {draft_name}")
        sections.append("=" * 60)
        sections.append(p.read_text(encoding="utf-8"))

        # Inline the evaluation for this draft
        eval_name = draft_name.replace("draft_", "eval_") + ".json"
        eval_path = materials_dir / eval_name
        if eval_path.exists():
            eval_data = json.loads(eval_path.read_text(encoding="utf-8"))
            score = eval_data.get("weighted_score", "?")
            sections.append("")
            sections.append(f"--- Evaluation for {draft_name} (weighted score: {score:.2f}) ---")
            for dim in eval_data.get("dimensions", []):
                qs = dim.get("questions", [])
                dim_score = sum(q.get("score", 0) for q in qs) / len(qs) if qs else 0
                sections.append(f"  {dim['name']}: {dim_score:.2f}")
                if dim.get("strengths"):
                    sections.append(f"    + {dim['strengths']}")
                if dim.get("weaknesses"):
                    sections.append(f"    - {dim['weaknesses']}")

    # Edgren dictionary context
    edgren_path = materials_dir / "edgren_context.txt"
    if edgren_path.exists():
        sections.append("")
        sections.append("=" * 60)
        sections.append("EDGREN ITALIAN-ENGLISH DICTIONARY (1901)")
        sections.append("=" * 60)
        sections.append(edgren_path.read_text(encoding="utf-8"))

    # Narrative context (just terminology + characters, skip the full JSON bulk)
    narrative_path = materials_dir / "narrative_context.json"
    if narrative_path.exists():
        nc = json.loads(narrative_path.read_text(encoding="utf-8"))
        sections.append("")
        sections.append("=" * 60)
        sections.append("NARRATIVE CONTEXT (characters & terminology)")
        sections.append("=" * 60)

        # Characters — compact format
        for group_name, group_key in [("Principal characters", "principals"),
                                       ("Di Rudio family", "di_rudio_family"),
                                       ("Orsini conspirators", "orsini_conspirators"),
                                       ("Historical figures", "historical_figures")]:
            chars = nc.get("characters", {}).get(group_key, [])
            if chars:
                sections.append(f"\n{group_name}:")
                for c in chars:
                    aliases = ", ".join(c.get("aliases", []))
                    alias_str = f" (also: {aliases})" if aliases else ""
                    sections.append(f"  - {c['name']}{alias_str}: {c.get('role', '')}")

        # Terminology — compact format
        for cat_name, cat_key in [("Political terms", "political"),
                                   ("Military terms", "military"),
                                   ("Legal terms", "legal"),
                                   ("Forms of address", "forms_of_address")]:
            terms = nc.get("terminology", {}).get(cat_key, {})
            if terms:
                sections.append(f"\n{cat_name}:")
                for term, gloss in terms.items():
                    sections.append(f"  - {term}: {gloss}")

    # Previous chapter translation (for continuity)
    if prev_chapter_text:
        sections.append("")
        sections.append("=" * 60)
        sections.append("PREVIOUS CHAPTER TRANSLATION (for voice/terminology continuity)")
        sections.append("=" * 60)
        sections.append(prev_chapter_text)

    brief_path = materials_dir / "synthesis_brief.md"
    brief_path.write_text("\n".join(sections), encoding="utf-8")
    return brief_path


def _build_synthesis_prompt(
    brief_path: Path,
    output_path: Path,
    has_prev_chapter: bool,
) -> str:
    """Build the prompt for the Claude Code Opus synthesis invocation."""
    prev_instr = (
        "7. Maintain consistency with the previous chapter's translation choices, "
        "register, and character voices"
    ) if has_prev_chapter else ""

    return SYNTHESIS_PROMPT_TEMPLATE.format(
        brief_path=brief_path,
        output_path=output_path,
        prev_chapter_instruction=prev_instr,
    )


def _build_provenance_prompt(brief_path: Path, output_path: Path, provenance_path: Path) -> str:
    """Build the prompt for the provenance logging invocation."""
    return PROVENANCE_PROMPT_TEMPLATE.format(
        brief_path=brief_path,
        output_path=output_path,
        provenance_path=provenance_path,
    )


# ── Core pipeline ────────────────────────────────────────────────────


def _extract_page_marker(text: str) -> tuple[str, str]:
    """Extract page marker comment and return (marker, clean_text)."""
    marker = ""
    match = re.search(r"<!-- pages:\d+-\d+ -->", text)
    if match:
        marker = match.group(0)
    clean = re.sub(r"<!-- pages:\d+-\d+ -->\n?", "", text)
    return marker, clean


def _build_edgren_context(text: str) -> str | None:
    """Build Edgren dictionary context for a chapter text."""
    from edgren import (
        chunk_edgren,
        edgren_entries_for_words,
        extract_content_words,
        format_edgren_context,
    )

    chunk_edgren()  # ensure chunks exist
    words = extract_content_words(text)
    entries = edgren_entries_for_words(words)
    return format_edgren_context(entries) if entries else None


def _generate_drafts(
    text: str,
    title: str,
    edgren_ctx: str | None,
    providers: list[TranslationProvider],
) -> list[tuple[str, TranslationResult]]:
    """Generate translation drafts from all providers in parallel.

    Returns list of (provider_name, TranslationResult) tuples.
    """
    results: list[tuple[str, TranslationResult]] = []

    if len(providers) == 1:
        p = providers[0]
        result = p.translate(text, title, SYSTEM_PROMPT, edgren_ctx)
        results.append((p.name, result))
    else:
        with ThreadPoolExecutor(max_workers=len(providers)) as pool:
            futures = {
                pool.submit(p.translate, text, title, SYSTEM_PROMPT, edgren_ctx): p
                for p in providers
            }
            for future in as_completed(futures):
                p = futures[future]
                result = future.result()
                results.append((p.name, result))

    return results


def _evaluate_drafts(
    italian_text: str,
    drafts: list[tuple[str, TranslationResult]],
    gemini_api_key: str | None = None,
) -> dict[str, dict]:
    """Evaluate all drafts using Gemini Flash (cheap, fast).

    Returns {provider_name: eval_result_dict} with scores and rationale.
    """
    from google import genai
    from google.genai import types
    from utils import retry_api_call

    key = gemini_api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise ValueError("No Gemini API key for evaluation. Set GEMINI_API_KEY.")
    client = genai.Client(api_key=key)

    dimensions_block = _build_dimensions_block()

    try:
        from google.api_core.exceptions import (
            InternalServerError,
            ResourceExhausted,
            ServiceUnavailable,
            TooManyRequests,
        )
        retryable = (ResourceExhausted, ServiceUnavailable,
                     InternalServerError, TooManyRequests)
    except ImportError:
        retryable = (RuntimeError,)

    def _eval_one(name: str, draft: TranslationResult) -> tuple[str, dict]:
        prompt = EVALUATION_PROMPT.format(
            italian_text=italian_text,
            model_name=name,
            translation_text=draft.text,
            dimensions_block=dimensions_block,
        )

        config = types.GenerateContentConfig(
            system_instruction="You are a literary translation quality evaluator. Respond only with valid JSON.",
            max_output_tokens=16_384,
            response_mime_type="application/json",
        )

        # Retry the full call (API + parse) up to 3 times on JSON errors
        last_error = None
        for attempt in range(3):
            def _call():
                return client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=prompt)],
                    ),
                    config=config,
                )

            response = retry_api_call(_call, retryable_exceptions=retryable)
            text = response.text.strip()

            # Strip markdown code fences if present
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)

            try:
                eval_result = json.loads(text)
                eval_result["weighted_score"] = _compute_weighted_score(eval_result)
                # Capture token usage from Gemini
                usage = getattr(response, "usage_metadata", None)
                eval_result["_tokens"] = {
                    "input": getattr(usage, "prompt_token_count", 0) if usage else 0,
                    "output": getattr(usage, "candidates_token_count", 0) if usage else 0,
                }
                return name, eval_result
            except json.JSONDecodeError as e:
                last_error = e
                print(f"      [{name}] JSON parse error on attempt {attempt + 1}: {e}")
                if attempt < 2:
                    time.sleep(2)

        raise RuntimeError(
            f"Evaluation of {name} failed after 3 attempts: {last_error}\n"
            f"Last response (first 500 chars): {text[:500]}"
        )

    # Evaluate all drafts in parallel
    results = {}
    if len(drafts) == 1:
        name, eval_result = _eval_one(drafts[0][0], drafts[0][1])
        results[name] = eval_result
    else:
        with ThreadPoolExecutor(max_workers=len(drafts)) as pool:
            futures = {
                pool.submit(_eval_one, name, draft): name
                for name, draft in drafts
            }
            for future in as_completed(futures):
                name, eval_result = future.result()
                results[name] = eval_result

    return results



def _run_claude_code(prompt: str, model: str, timeout: int, label: str) -> subprocess.CompletedProcess:
    """Run a claude -p invocation and return the result."""
    cmd = [
        "claude",
        "-p", prompt,
        "--model", model,
        "--output-format", "json",
        "--allowedTools", "Read,Write,Bash(ls)",
        "--bare",
    ]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


# Quotations, foreign/Latin citations, and proper names must survive synthesis
# verbatim, and the body must not shrink. The synthesis layer has been observed to
# silently drop both (a Dante quotation, whole thesis sentences) without trace:
# provenance.json logs only cross-draft *swaps*, never *omissions*. This guard
# re-derives what should have carried over from the drafts and logs anything
# missing at synthesis time, instead of leaving it for a later source-aware audit.
def _norm_words(text: str) -> list[str]:
    """Lowercased word tokens with punctuation stripped — for language-agnostic
    verbatim matching across source, drafts and synthesis (so differing quote
    styles or trailing punctuation can't hide a real carry-over)."""
    return re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE).lower().split()


def _dropped_carryovers(source: str, drafts: list[str], synthesis: str, w: int = 5) -> list[str]:
    """Verbatim multi-word runs shared by the source and a draft but missing here.

    A run of >=w words appearing unchanged in the Italian source and in EVERY
    draft is untranslated material that the editorial convention keeps verbatim —
    a Latin tag, a line of verse, a multi-word name. Requiring consensus across
    all drafts is what separates these from a source quote that some drafts simply
    translate (which the synthesis is right to render in English, not a drop).
    Adjacent flagged runs are merged into the maximal dropped span.
    """
    sw = _norm_words(source)
    norm_drafts = [" ".join(_norm_words(d)) for d in drafts]
    norm_syn = " ".join(_norm_words(synthesis))
    flagged = [False] * len(sw)
    for i in range(len(sw) - w + 1):
        phrase = " ".join(sw[i:i + w])
        if all(phrase in nd for nd in norm_drafts) and phrase not in norm_syn:
            for j in range(i, i + w):
                flagged[j] = True
    spans, i = [], 0
    while i < len(sw):
        if flagged[i]:
            j = i
            while j < len(sw) and flagged[j]:
                j += 1
            spans.append(" ".join(sw[i:j]))
            i = j
        else:
            i += 1
    return spans


def _check_synthesis_integrity(
    chapter_id: str, translation: str, materials_dir: Path
) -> list[str]:
    """Flag content the synthesis dropped relative to its drafts (deterministic log).

    Catches the two failure modes provenance.json cannot record — dropped
    quotations/citations and dropped paragraphs/sentences — by comparing the
    synthesis against its own drafts. Writes synthesis_integrity.json and returns
    the warnings (empty list = clean).
    """
    draft_paths = sorted(materials_dir.glob("draft_*.md"))
    drafts = [p.read_text(encoding="utf-8") for p in draft_paths]
    source = ""
    src_path = materials_dir / "italian_source.txt"
    if src_path.exists():
        source = src_path.read_text(encoding="utf-8")
    warnings: list[str] = []

    if drafts and source:
        # A. Untranslatable carry-overs the synthesis dropped: multi-word verbatim
        #    runs shared by the source and a draft, plus ALL-CAPS names by the same
        #    "in source + a draft, missing here" logic (the draft filter excludes
        #    ordinary quotes that get translated, keeping false positives low).
        for span in _dropped_carryovers(source, drafts, translation):
            warnings.append(f"dropped carry-over (source + a draft, missing here): {span!r}")
        caps = {t for t in re.findall(r"\b[A-ZÀ-Ý][A-ZÀ-Ý]{2,}\b", source)}
        for name in sorted(caps):
            if all(name in d for d in drafts) and name not in translation:
                warnings.append(f"dropped ALL-CAPS name (source + all drafts, missing here): {name!r}")

        # B. Gross shrinkage — body far shorter than the draft median signals a
        #    dropped paragraph. Conservative (<85%) because synthesis legitimately
        #    paragraphs and tightens differently from the drafts; a single dropped
        #    sentence in a long chapter is below this floor and still needs the
        #    periodic source-aware audit to catch.
        n_words = lambda t: len(t.split())
        med = sorted(n_words(d) for d in drafts)[len(drafts) // 2]
        if med and n_words(translation) < 0.85 * med:
            warnings.append(
                f"body {n_words(translation)} words vs median draft {med} "
                f"(<85%) — possible dropped paragraph"
            )

    log = {
        "chapter_id": chapter_id,
        "drafts_compared": [p.name for p in draft_paths],
        "warnings": warnings,
    }
    (materials_dir / "synthesis_integrity.json").write_text(
        json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    if warnings:
        print(f"      [{chapter_id}] ⚠ synthesis integrity: {len(warnings)} warning(s)")
        for w in warnings:
            print(f"          - {w}")
    return warnings


def _synthesize_via_claude_code(
    chapter_id: str,
    n_drafts: int,
    has_prev_chapter: bool,
    prev_chapter_text: str | None,
    state_dir: Path,
    synth_model: str = "opus",
) -> tuple[str, dict]:
    """Invoke Claude Code Opus to synthesise the best translation.

    Two sequential calls:
      1. Synthesis — produces the translation (critical, longer timeout)
      2. Provenance — documents what was done (best-effort, shorter timeout)

    All materials are pre-assembled into a single synthesis_brief.md so Opus
    needs only one Read call instead of 6-8 (dramatically reduces token usage).

    Returns (translated_text, token_data_dict).
    """
    materials_dir = state_dir / "multi_drafts" / chapter_id
    output_path = state_dir / "translations" / f"{chapter_id}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Assemble all materials into a single brief file
    brief_path = _assemble_synthesis_brief(materials_dir, prev_chapter_text)

    # ── Step 1: Synthesis (critical) ─────────────────────────────────

    synth_prompt = _build_synthesis_prompt(
        brief_path=brief_path,
        output_path=output_path,
        has_prev_chapter=has_prev_chapter,
    )

    result = _run_claude_code(synth_prompt, synth_model, timeout=1800, label=f"synthesis:{chapter_id}")

    if result.returncode != 0:
        raise RuntimeError(
            f"Synthesis failed for {chapter_id} "
            f"(exit {result.returncode}): {result.stderr[:500]}"
        )

    # Verify the output file was written
    if not output_path.exists():
        try:
            response = json.loads(result.stdout)
            if isinstance(response, list):
                result_entry = next((e for e in response if e.get("type") == "result"), {})
            else:
                result_entry = response
            text = result_entry.get("result", "")
            if text:
                output_path.write_text(text, encoding="utf-8")
            else:
                raise RuntimeError(
                    f"Synthesis for {chapter_id} produced no output file and no result text"
                )
        except (json.JSONDecodeError, KeyError):
            raise RuntimeError(
                f"Synthesis for {chapter_id} produced no output file "
                f"and response was not parseable"
            )

    translation = output_path.read_text(encoding="utf-8")

    # Deterministic integrity guard: log anything the synthesis dropped vs its
    # drafts. provenance.json (written below) records only swaps, never omissions.
    _check_synthesis_integrity(chapter_id, translation, materials_dir)

    # Parse synthesis token usage from Claude Code JSON response.
    # Output is a JSON array; the last entry has type="result" with cost/usage.
    synth_tokens = {"input": 0, "output": 0}
    try:
        response_data = json.loads(result.stdout)
        if isinstance(response_data, list):
            result_entry = next((e for e in response_data if e.get("type") == "result"), {})
        else:
            result_entry = response_data
        synth_tokens["cost_usd"] = result_entry.get("total_cost_usd", 0)
        synth_tokens["duration_ms"] = result_entry.get("duration_ms", 0)
        synth_tokens["num_turns"] = result_entry.get("num_turns", 0)
        usage = result_entry.get("usage", {})
        synth_tokens["input"] = usage.get("input_tokens", 0)
        synth_tokens["output"] = usage.get("output_tokens", 0)
    except (json.JSONDecodeError, KeyError, TypeError):
        pass

    # ── Step 2: Provenance (best-effort) ─────────────────────────────

    provenance_path = materials_dir / "provenance.json"
    prov_prompt = _build_provenance_prompt(brief_path, output_path, provenance_path)
    prov_tokens = {"input": 0, "output": 0}

    try:
        prov_result = _run_claude_code(prov_prompt, synth_model, timeout=600, label=f"provenance:{chapter_id}")

        if prov_result.returncode != 0:
            print(f"      [{chapter_id}] Provenance logging failed (exit {prov_result.returncode}), skipping")
        elif not provenance_path.exists():
            print(f"      [{chapter_id}] Provenance file not written, skipping")
        else:
            print(f"      [{chapter_id}] Provenance log written")
            try:
                prov_data = json.loads(prov_result.stdout)
                if isinstance(prov_data, list):
                    prov_entry = next((e for e in prov_data if e.get("type") == "result"), {})
                else:
                    prov_entry = prov_data
                prov_tokens["cost_usd"] = prov_entry.get("total_cost_usd", 0)
                prov_tokens["duration_ms"] = prov_entry.get("duration_ms", 0)
                prov_usage = prov_entry.get("usage", {})
                prov_tokens["input"] = prov_usage.get("input_tokens", 0)
                prov_tokens["output"] = prov_usage.get("output_tokens", 0)
            except (json.JSONDecodeError, KeyError, TypeError):
                pass
    except subprocess.TimeoutExpired:
        print(f"      [{chapter_id}] Provenance logging timed out, skipping")

    return translation, {"synthesis": synth_tokens, "provenance": prov_tokens}


# ── Main entry point ─────────────────────────────────────────────────


def multi_translate(
    output_dir: Path,
    state_dir: Path,
    *,
    api_key: str | None = None,
    gemini_api_key: str | None = None,
    openai_api_key: str | None = None,
    draft_models: tuple[str, ...] = ("claude", "gemini"),
    workers: int = 1,
    thinking_budget: int = 4096,
    with_edgren: bool = True,
    synth_model: str = "opus",
    chapter_filter: list[str] | None = None,
) -> None:
    """Multi-witness translation: draft → evaluate → synthesise.

    Args:
        output_dir: Where italian_clean.md lives and english_translation.md is written.
        state_dir: Working state directory (translations/, multi_drafts/, etc.).
        api_key: Anthropic API key.
        gemini_api_key: Gemini API key.
        openai_api_key: OpenAI API key (optional, for GPT drafts).
        draft_models: Tuple of model names to generate drafts from.
        workers: Max concurrent chapters to process in parallel during draft phase.
        thinking_budget: Extended thinking token budget for Anthropic draft provider.
        with_edgren: Whether to enrich prompts with Edgren 1901 dictionary context.
        synth_model: Model for Claude Code synthesis (default: opus).
        chapter_filter: Optional list of chapter IDs to process (None = all).
    """
    from utils import atomic_write_json

    italian_path = output_dir / "italian_clean.md"
    italian_text = italian_path.read_text(encoding="utf-8")
    chapters = parse_italian_markdown(italian_text)

    # Filter chapters if requested
    if chapter_filter:
        filter_set = set(chapter_filter)
        chapters = [ch for ch in chapters if ch["id"] in filter_set]

    print(f"  Multi-witness translation: {len(chapters)} chapters")
    print(f"  Draft models: {', '.join(draft_models)}")
    print(f"  Synthesis: Claude Code ({synth_model})")
    print(f"  Edgren context: {'yes' if with_edgren else 'no'}")

    # ── Initialise providers ─────────────────────────────────────────

    providers = []
    for model_name in draft_models:
        providers.append(create_provider(
            model_name,
            anthropic_api_key=api_key,
            gemini_api_key=gemini_api_key,
            openai_api_key=openai_api_key,
            thinking_budget=thinking_budget,
        ))
    print(f"  Providers initialised: {[p.name for p in providers]}")

    # ── Load progress ────────────────────────────────────────────────

    translations_dir = state_dir / "translations"
    translations_dir.mkdir(parents=True, exist_ok=True)

    progress_path = state_dir / "multi_translate_progress.json"
    if progress_path.exists():
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
    else:
        progress = {}

    # ── Phase 1 & 2: Draft + Evaluate (parallelisable across chapters) ──

    drafts_dir = state_dir / "multi_drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)

    progress_lock = threading.Lock()

    def _draft_and_evaluate(ch: dict) -> None:
        """Generate drafts and evaluate for a single chapter.

        Each phase is durable: drafts are saved to disk immediately so that
        a failure during evaluation does not lose the expensive draft work.
        On resume, completed phases are skipped.
        """
        ch_id = ch["id"]
        ch_progress = progress.get(ch_id, {})
        current_phase = ch_progress.get("phase")

        # Skip if already fully evaluated or beyond
        if current_phase in ("evaluated", "synthesizing", "done"):
            return

        page_marker, clean_text = _extract_page_marker(ch["text"])
        materials_dir = state_dir / "multi_drafts" / ch_id
        materials_dir.mkdir(parents=True, exist_ok=True)

        # Build Edgren context (needed by both draft and materials)
        edgren_ctx = None
        if with_edgren:
            edgren_ctx = _build_edgren_context(clean_text)

        # ── Draft phase (skip if already drafted) ────────────────────
        if current_phase != "drafted":
            print(f"    [{ch_id}] Drafting ({len(clean_text):,} chars)...")
            with progress_lock:
                progress[ch_id] = {"phase": "drafting", "page_marker": page_marker}
                atomic_write_json(progress_path, progress)

            t0 = time.monotonic()
            drafts = _generate_drafts(clean_text, ch["title"], edgren_ctx, providers)
            draft_elapsed = time.monotonic() - t0

            draft_summary = ", ".join(
                f"{name}: {r.elapsed:.0f}s/{r.output_tokens:,}tok"
                for name, r in drafts
            )
            print(f"    [{ch_id}] Drafts done ({draft_elapsed:.0f}s) — {draft_summary}")

            # Persist drafts + source + context immediately so they survive eval failures
            (materials_dir / "italian_source.txt").write_text(clean_text, encoding="utf-8")
            if edgren_ctx:
                (materials_dir / "edgren_context.txt").write_text(edgren_ctx, encoding="utf-8")
            # Copy narrative context (shared across all chapters)
            narrative_ctx_src = Path(__file__).parent / "data" / "narrative_context.json"
            if narrative_ctx_src.exists():
                shutil.copy2(narrative_ctx_src, materials_dir / "narrative_context.json")
            for name, draft in drafts:
                safe_name = re.sub(r"[^a-z0-9]", "_", name.lower()).strip("_")
                (materials_dir / f"draft_{safe_name}.md").write_text(draft.text, encoding="utf-8")

            with progress_lock:
                progress[ch_id] = {
                    "phase": "drafted",
                    "page_marker": page_marker,
                    "draft_models": [name for name, _ in drafts],
                    "tokens": {
                        "drafts": {
                            name: {"input": r.input_tokens, "output": r.output_tokens}
                            for name, r in drafts
                        },
                    },
                }
                atomic_write_json(progress_path, progress)
        else:
            # Resume: reload drafts from disk
            print(f"    [{ch_id}] Drafts already on disk, resuming at evaluation...")
            draft_names = ch_progress.get("draft_models", [])
            drafts = []
            for name in draft_names:
                safe_name = re.sub(r"[^a-z0-9]", "_", name.lower()).strip("_")
                draft_path = materials_dir / f"draft_{safe_name}.md"
                if draft_path.exists():
                    text = draft_path.read_text(encoding="utf-8")
                    drafts.append((name, TranslationResult(
                        text=text, model=name,
                        input_tokens=0, output_tokens=0, elapsed=0, stop_reason="resumed",
                    )))

        # ── Evaluate phase ───────────────────────────────────────────
        print(f"    [{ch_id}] Evaluating {len(drafts)} drafts...")
        t0 = time.monotonic()
        evaluations = _evaluate_drafts(clean_text, drafts, gemini_api_key)
        eval_elapsed = time.monotonic() - t0

        score_summary = ", ".join(
            f"{name}: {ev['weighted_score']:.2f}"
            for name, ev in evaluations.items()
        )
        print(f"    [{ch_id}] Evaluation done ({eval_elapsed:.0f}s) — {score_summary}")

        # Persist evaluations
        for name, eval_result in evaluations.items():
            safe_name = re.sub(r"[^a-z0-9]", "_", name.lower()).strip("_")
            (materials_dir / f"eval_{safe_name}.json").write_text(
                json.dumps(eval_result, indent=2, ensure_ascii=False), encoding="utf-8"
            )

        # Merge token data: keep draft tokens from prior phase, add eval tokens
        existing_tokens = progress.get(ch_id, {}).get("tokens", {})
        existing_tokens["evals"] = {
            name: ev.get("_tokens", {"input": 0, "output": 0})
            for name, ev in evaluations.items()
        }

        with progress_lock:
            progress[ch_id] = {
                "phase": "evaluated",
                "page_marker": page_marker,
                "draft_models": [name for name, _ in drafts],
                "scores": {name: ev["weighted_score"] for name, ev in evaluations.items()},
                "tokens": existing_tokens,
            }
            atomic_write_json(progress_path, progress)

    # Run draft+evaluate in parallel across chapters
    todo = [
        ch for ch in chapters
        if progress.get(ch["id"], {}).get("phase") not in ("evaluated", "synthesizing", "done")
    ]

    if todo:
        print(f"\n  Phase 1-2: Drafting and evaluating {len(todo)} chapters...")
        effective_workers = min(workers, len(todo))
        if effective_workers <= 1:
            for ch in todo:
                _draft_and_evaluate(ch)
        else:
            with ThreadPoolExecutor(max_workers=effective_workers) as pool:
                futures = {pool.submit(_draft_and_evaluate, ch): ch for ch in todo}
                for future in as_completed(futures):
                    exc = future.exception()
                    if exc:
                        ch = futures[future]
                        print(f"    [{ch['id']}] ERROR in draft/eval: {exc}")
                        with progress_lock:
                            progress[ch["id"]] = {
                                "phase": "error",
                                "error": str(exc),
                            }
                            atomic_write_json(progress_path, progress)
    else:
        print("\n  Phase 1-2: All chapters already drafted and evaluated.")

    # ── Phase 3: Synthesis (sequential for chapter continuity) ───────

    synth_todo = [
        ch for ch in chapters
        if progress.get(ch["id"], {}).get("phase") in ("evaluated", "synthesizing")
    ]

    if synth_todo:
        print(f"\n  Phase 3: Synthesising {len(synth_todo)} chapters (sequential)...")

        # Seed prev_chapter_text from the last already-done chapter preceding
        # the first synth_todo entry (needed for resume continuity).
        prev_chapter_text = None
        first_synth_id = synth_todo[0]["id"]
        all_chapter_ids = [ch["id"] for ch in chapters]
        first_synth_idx = all_chapter_ids.index(first_synth_id) if first_synth_id in all_chapter_ids else 0
        if first_synth_idx > 0:
            prev_id = all_chapter_ids[first_synth_idx - 1]
            prev_path = state_dir / "translations" / f"{prev_id}.md"
            if prev_path.exists():
                prev_chapter_text = prev_path.read_text(encoding="utf-8")
                print(f"    (seeded prev_chapter context from {prev_id})")

        for i, ch in enumerate(synth_todo):
            ch_id = ch["id"]
            ch_progress = progress.get(ch_id, {})
            page_marker = ch_progress.get("page_marker", "")

            n_drafts = len(draft_models)
            has_prev = prev_chapter_text is not None

            print(f"    [{i+1}/{len(synth_todo)}] Synthesising: {ch['title']}...")
            with progress_lock:
                progress[ch_id]["phase"] = "synthesizing"
                atomic_write_json(progress_path, progress)

            t0 = time.monotonic()
            try:
                synthesized, cc_tokens = _synthesize_via_claude_code(
                    ch_id, n_drafts, has_prev, prev_chapter_text,
                    state_dir, synth_model,
                )
                elapsed = time.monotonic() - t0

                # Reinsert page marker and ensure file is up to date
                if page_marker:
                    synthesized = page_marker + "\n\n" + synthesized
                output_path = state_dir / "translations" / f"{ch_id}.md"
                output_path.write_text(synthesized, encoding="utf-8")

                synth_cost = cc_tokens.get("synthesis", {}).get("cost_usd", 0)
                prov_cost = cc_tokens.get("provenance", {}).get("cost_usd", 0)
                cost_str = f" ${synth_cost + prov_cost:.3f}" if synth_cost else ""
                print(f"    [{i+1}/{len(synth_todo)}] {ch['title']}: done "
                      f"({len(synthesized):,} chars) [{elapsed:.1f}s]{cost_str}")

                with progress_lock:
                    existing_tokens = progress[ch_id].get("tokens", {})
                    existing_tokens["synthesis"] = cc_tokens
                    progress[ch_id]["phase"] = "done"
                    progress[ch_id]["tokens"] = existing_tokens
                    atomic_write_json(progress_path, progress)

                # This chapter becomes context for the next
                prev_chapter_text = synthesized

            except Exception as e:
                elapsed = time.monotonic() - t0
                print(f"    [{i+1}/{len(synth_todo)}] {ch['title']}: "
                      f"SYNTHESIS ERROR [{elapsed:.1f}s] — {e}")
                with progress_lock:
                    progress[ch_id]["phase"] = "error"
                    progress[ch_id]["error"] = str(e)
                    atomic_write_json(progress_path, progress)
                # Still pass whatever we have as prev context for subsequent chapters
                existing = state_dir / "translations" / f"{ch_id}.md"
                if existing.exists():
                    prev_chapter_text = existing.read_text(encoding="utf-8")
    else:
        print("\n  Phase 3: All chapters already synthesised.")

    # ── Assemble final English markdown ──────────────────────────────

    # Re-parse full chapter list for assembly (not just filtered)
    all_chapters = parse_italian_markdown(
        (output_dir / "italian_clean.md").read_text(encoding="utf-8")
    )
    assemble_translation(output_dir, state_dir, all_chapters)

    # ── Summary with token expenditure ────────────────────────────────

    done = sum(1 for v in progress.values() if v.get("phase") == "done")
    errors = sum(1 for v in progress.values() if v.get("phase") == "error")
    print(f"\n  Complete: {done} synthesised, {errors} errors")

    # Token expenditure table
    chapters_with_tokens = [
        (ch_id, data) for ch_id, data in progress.items()
        if data.get("tokens")
    ]
    if chapters_with_tokens:
        print(f"\n  {'Chapter':<30} {'Draft In':>10} {'Draft Out':>10} {'Eval In':>10} {'Eval Out':>10} {'Synth $':>10}")
        print(f"  {'-'*30} {'-'*10} {'-'*10} {'-'*10} {'-'*10} {'-'*10}")

        totals = {"draft_in": 0, "draft_out": 0, "eval_in": 0, "eval_out": 0, "synth_cost": 0.0}

        for ch_id, data in chapters_with_tokens:
            tokens = data.get("tokens", {})

            # Draft tokens (sum across models)
            draft_in = sum(d.get("input", 0) for d in tokens.get("drafts", {}).values())
            draft_out = sum(d.get("output", 0) for d in tokens.get("drafts", {}).values())

            # Eval tokens (sum across models)
            eval_in = sum(e.get("input", 0) for e in tokens.get("evals", {}).values())
            eval_out = sum(e.get("output", 0) for e in tokens.get("evals", {}).values())

            # Synthesis cost (from Claude Code)
            synth_data = tokens.get("synthesis", {})
            synth_cost = synth_data.get("synthesis", {}).get("cost_usd", 0)
            prov_cost = synth_data.get("provenance", {}).get("cost_usd", 0)
            total_cc_cost = synth_cost + prov_cost

            totals["draft_in"] += draft_in
            totals["draft_out"] += draft_out
            totals["eval_in"] += eval_in
            totals["eval_out"] += eval_out
            totals["synth_cost"] += total_cc_cost

            cost_str = f"${total_cc_cost:.3f}" if total_cc_cost else "—"
            print(f"  {ch_id:<30} {draft_in:>10,} {draft_out:>10,} {eval_in:>10,} {eval_out:>10,} {cost_str:>10}")

        print(f"  {'-'*30} {'-'*10} {'-'*10} {'-'*10} {'-'*10} {'-'*10}")
        cost_str = f"${totals['synth_cost']:.3f}" if totals["synth_cost"] else "—"
        print(f"  {'TOTAL':<30} {totals['draft_in']:>10,} {totals['draft_out']:>10,} {totals['eval_in']:>10,} {totals['eval_out']:>10,} {cost_str:>10}")
