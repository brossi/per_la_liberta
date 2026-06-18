"""Stage 2 of the intention-review track: a PROPOSAL engine, not a decision engine.

Stage 1 (comprehension.py) flags passages that read wrong in English, blind to
the source. Stage 2 brings the Italian back in and, for each flag, drafts a
proposal the human approves/edits/rejects — turning the reviewer from author
into editor. It NEVER applies anything; it only proposes.

Per flag it produces {verdict, confidence, draft, rationale} from a PROPOSER
model given the full bilingual context (English window + aligned Italian + neutral
MT + the panel's own rationales), then an independent CHECKER model (different
architecture) judges whether the draft faithfully renders the Italian without
adding or dropping meaning, and whether it agrees with the verdict. The checker
is the guard against fluent-wrong: where proposer and checker disagree, the item
is surfaced AS contested rather than hidden behind a confident draft.

    uv run python stage2.py --anchors "chyle,Chancellor"   # pilot on specific flags
    uv run python stage2.py --breadth 3 --severity high     # the major-items tier

Output: state/comprehension/proposals.jsonl (one record per flag).
"""

import argparse
import json
import os
import re

from dotenv import load_dotenv

from align import italian_window
from comprehension import OUT_DIR, build_units
import mt

PROPOSALS = os.path.join(OUT_DIR, "proposals.jsonl")

PROPOSER_SYSTEM = """You are the editor of an English literary translation of a 1913 Italian memoir (Cesare Crespi on Carlo di Rudio and the Orsini conspiracy). A comprehension reviewer has flagged a passage of OUR English translation as hard to understand. You now have the Italian source. Decide what to do and, if a fix is warranted, draft it.

You are given:
- OUR ENGLISH (the flagged passage, with the flagged span marked «like this»), plus neighbouring English for context;
- the ITALIAN SOURCE (aligned, may include a neighbouring paragraph);
- a NEUTRAL MACHINE TRANSLATION of the Italian (DeepL — a sense-based reference, not authoritative);
- the REVIEWER NOTES explaining what a reader could not resolve.

Choose exactly one verdict:
- retranslate — our English misrenders or obscures the Italian (a literal idiom-calque, a false friend, garden-path word order, a real mistranslation). The Italian is clear; we failed it.
- gloss — our English is FAITHFUL but the source contains an allusion or term opaque to a modern reader (Dante, a historical nickname, a literary reference like Eugène Sue's "Pipelet"). Keep the text; add a footnote.
- leave — our English is faithful and the difficulty is IN THE SOURCE itself (the Italian is equally abstract/vague/elliptical). Do not manufacture a clarity the original lacks.
- recoverable — a real but minor awkwardness a reader resolves on a second pass; not worth a change.

Rules for a `retranslate` draft:
- Render the MEANING in natural English of the period's elevated literary register, American spelling. Do NOT calque the Italian image; do NOT modernise into plain contemporary prose.
- FAITHFULNESS IS ABSOLUTE: add no meaning not in the Italian, drop none that is. If you are unsure what the Italian means, choose `leave` and say so — never invent.
- CROSS-CHECK CONCRETE TERMS AGAINST THE NEUTRAL MT. Where our English and the MT diverge on a specific noun, title, rank, office, or object (e.g. our "Chancellor" vs the MT's "court clerk" for *Cancelliere*), the MT's sense is usually right and our word is a false friend — fix it, even if the reviewer did not name it. The MT is unreliable on idioms and on register, so do NOT follow it there; use it only to check concrete terms.
- Change as little as possible — ideally rewrite only the flagged sentence. Keep proper names as in the source.
- The draft must be a drop-in replacement for the flagged sentence (or the smallest span that fixes it).

Rules for a `gloss` draft: write the footnote text itself (one or two sentences identifying the allusion), not a rewrite.

OUTPUT — record-delimited, NOT JSON:
@@PROP
verdict: retranslate|gloss|leave|recoverable
confidence: high|medium|low
draft: <single line: the replacement sentence (retranslate) OR the footnote text (gloss); a single hyphen "-" if leave/recoverable>
rationale: <prose: why this verdict; for retranslate, name the specific Italian word/idiom and how your draft renders it. May run several lines.>
@@END
Output the block and nothing else."""

CHECKER_SYSTEM = """You are an independent bilingual checker (Italian↔English) for a literary translation. Another editor has proposed a verdict and possibly a draft fix for a flagged passage. Your ONLY job is to guard against confident-but-wrong proposals. Be skeptical.

You are given the ITALIAN SOURCE, OUR ORIGINAL ENGLISH, and the EDITOR'S PROPOSAL (verdict + draft).

Judge two things:
1. FAITHFUL — if the proposal is a `retranslate` draft, does it render the Italian with NO added meaning and NO dropped meaning? (A fluent sentence that says something the Italian does not is NOT faithful.) For gloss/leave/recoverable with no draft, judge whether the verdict itself is defensible.
2. VERDICT_AGREE — do you agree with the chosen verdict, given the Italian? (e.g. if the editor says retranslate but the Italian is itself just as vague, you should disagree and lean `leave`.)

Default to skepticism: if the draft adds an interpretation, smooths over a genuine ambiguity in the source, or you cannot verify it against the Italian, mark faithful: no or partial.

Then GRADE what the proposal needs (fix_needed):
- none — approve as-is; faithful and the verdict is right.
- minor — the substance is right but a small edit would perfect it (a register or word-choice tweak, e.g. an idiom rendered with the right sense but a too-colloquial word; a gloss whose facts should be verified).
- major — needs human rethinking: the draft adds or drops meaning, rewrites on a guess about an ambiguous source, leaves a clear lexical error unfixed (a false friend the Italian contradicts), or you cannot verify it against the Italian; OR you disagree with the verdict.

OUTPUT — record-delimited, NOT JSON:
@@CHECK
faithful: yes|partial|no
verdict_agree: yes|no
fix_needed: none|minor|major
note: <prose: what is added/dropped/unverifiable, or why you disagree. May run several lines.>
@@END
Output the block and nothing else."""


def _mark(target: str, anchor: str) -> str:
    i = target.lower().find(anchor.lower())
    if i < 0:
        return target
    return target[:i] + "«" + target[i:i + len(anchor)] + "»" + target[i + len(anchor):]


def proposer_context(c: dict, unit: dict) -> str:
    it = italian_window(c["chapter"], c["idx"], radius=1)
    mtxt = mt.cached((italian_window(c["chapter"], c["idx"], radius=0) or {}).get("text", ""))
    notes = "\n".join(f"- ({g['severity']}/{g['category']}) {g['why']}" for g in c.get("rationales", []))
    return (
        f"OUR ENGLISH (flagged span in «»):\n"
        f"[prev] {unit.get('prev') or '—'}\n[TARGET] {_mark(unit.get('target',''), c['anchor'])}\n[next] {unit.get('next') or '—'}\n\n"
        f"ITALIAN SOURCE:\n{(it or {}).get('text','—')}\n\n"
        f"NEUTRAL MACHINE TRANSLATION (DeepL):\n{mtxt or '—'}\n\n"
        f"REVIEWER NOTES (why it was flagged):\n{notes}"
    )


def checker_context(c: dict, unit: dict, prop: dict) -> str:
    it = italian_window(c["chapter"], c["idx"], radius=1)
    return (
        f"ITALIAN SOURCE:\n{(it or {}).get('text','—')}\n\n"
        f"OUR ORIGINAL ENGLISH:\n{unit.get('target','')}\n\n"
        f"EDITOR'S PROPOSAL:\nverdict: {prop.get('verdict')}\ndraft: {prop.get('draft') or '—'}\n"
        f"rationale: {prop.get('rationale','')}"
    )


# ── parameterized callers (own system prompt) ────────────────────────


def call_claude(system: str, user: str, model="claude-opus-4-6") -> str:
    import anthropic
    c = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=300)
    r = c.messages.create(model=model, max_tokens=4000, system=system,
                          messages=[{"role": "user", "content": user}])
    return "".join(b.text for b in r.content if b.type == "text")


def call_gpt(system: str, user: str, model="gpt-5.4") -> str:
    import openai
    c = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=240)
    r = c.chat.completions.create(model=model, max_completion_tokens=4000, reasoning_effort="low",
                                  messages=[{"role": "system", "content": system},
                                            {"role": "user", "content": user}])
    return r.choices[0].message.content or ""


def _parse(raw: str, keys: set[str], prose_key: str) -> dict:
    """Parse one record-delimited block: scalar `key: value` lines + one trailing prose field."""
    out = {}
    cur = None
    for line in raw.splitlines():
        m = re.match(r"\s*([a-z_]+)\s*:\s*(.*)$", line)
        if m and m.group(1) in keys:
            cur = m.group(1)
            out[cur] = m.group(2).strip()
        elif cur == prose_key:
            out[prose_key] = (out.get(prose_key, "") + "\n" + line).strip()
    return out


def propose_one(c: dict, unit: dict) -> dict:
    raw = call_claude(PROPOSER_SYSTEM, proposer_context(c, unit))
    prop = _parse(raw, {"verdict", "confidence", "draft", "rationale"}, "rationale")
    raw_chk = call_gpt(CHECKER_SYSTEM, checker_context(c, unit, prop))
    chk = _parse(raw_chk, {"faithful", "verdict_agree", "fix_needed", "note"}, "note")
    return {"chapter": c["chapter"], "idx": c["idx"], "anchor": c["anchor"],
            "category": c["category"], "severity": c["severity"], "breadth": c["breadth"],
            "score": c["score"], "proposal": prop, "check": chk}


def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 2 proposal engine (proposes, never applies)")
    ap.add_argument("--anchors", default="", help="comma-separated anchor substrings (pilot mode)")
    ap.add_argument("--breadth", type=int, default=3)
    ap.add_argument("--severity", choices=["high", "medium", "low"], default=None)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

    rows = [json.loads(l) for l in open(os.path.join(OUT_DIR, "flags.jsonl"), encoding="utf-8")]
    if args.anchors:
        subs = [s.strip().lower() for s in args.anchors.split(",")]
        rows = [r for r in rows if any(s in r["anchor"].lower() for s in subs)]
    else:
        rows = [r for r in rows if r["breadth"] >= args.breadth
                and (not args.severity or r["severity"] == args.severity)]
        rows.sort(key=lambda r: r["score"], reverse=True)
    if args.limit:
        rows = rows[: args.limit]

    units = {(u["chapter"], u["idx"]): u for u in build_units()}
    results = []
    for i, c in enumerate(rows, 1):
        u = units.get((c["chapter"], c["idx"]), {})
        res = propose_one(c, u)
        results.append(res)
        p, ck = res["proposal"], res["check"]
        grade = ck.get("fix_needed", "?")
        tag = {"none": "✓ ready", "minor": "› quick-edit", "major": "⚠ needs-you"}.get(grade, f"? {grade}")
        print(f"[{i}/{len(rows)}] {c['chapter']} ¶{c['idx']} — {p.get('verdict','?')}/{p.get('confidence','?')}  [{tag}]")
        print(f"    flag : «{c['anchor']}»")
        print(f"    draft: {p.get('draft','—')}")
        print(f"    check: faithful={ck.get('faithful','?')} agree={ck.get('verdict_agree','?')} fix={grade} — {ck.get('note','')[:150]}")
        print()
    with open(PROPOSALS, "w", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    from collections import Counter
    grades = Counter(r["check"].get("fix_needed", "?") for r in results)
    print(f"wrote {len(results)} proposals → {PROPOSALS}")
    print(f"  grades: ready={grades['none']}  quick-edit={grades['minor']}  needs-you={grades['major']}")


if __name__ == "__main__":
    main()
