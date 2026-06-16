"""Stage 1 of the intention-review track: blind English-only comprehension review.

Non-destructive collection. A 3-model panel (claude-opus-4-6, gemini-3.5-flash,
gpt-5.4), N samples each, reads ONLY the English translation — no Italian — and
flags passages a careful reader cannot confidently make sense of on one read.
Seeing the source biases a reviewer to forgive translationese, so this pass is
source-blind by design; the bilingual intention pass (stage 2) is separate.

Unit of review is a sliding window: the target passage plus one neighbour on
each side. Only the target is judged; the neighbours exist so the panel can
resolve pronouns and event-chains that cross paragraph boundaries.

Model output is record-delimited, NOT JSON: the rationale field is free prose
and the anchors quote source text containing quotation marks, both of which
break JSON atomically. Extraction is a validated contract — every flag's anchor
must resolve to real target-passage text, or the call is retried; an exhausted
call is marked needs-rerun, never silently emptied (a junk response and an
honest "nothing wrong" must not look identical).

Reads  output/english_translation.md   (English only — no Italian dependency)
Writes state/comprehension/             (gitignored: raw outputs + ranked ledger)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
load_dotenv(os.path.join(ROOT, ".env"))

ENGLISH_MD = os.path.join(ROOT, "output", "english_translation.md")
ITALIAN_MD = os.path.join(ROOT, "output", "italian_clean.md")
OUT_DIR = os.path.join(ROOT, "state", "comprehension")

PANEL = ["claude-opus-4-6", "gemini-3.5-flash", "gpt-5.4"]
SAMPLES = 2
MAX_ATTEMPTS = 3          # per (passage, model, sample) call before marking needs-rerun
WORKERS = 12
GPT_REASONING = "low"     # validated on-target at Ch.18; tunable

CATEGORIES = {"referent", "event-chain", "garden-path", "translationese",
              "grammar", "opaque-term", "awkward", "other"}
LEVELS = {"high", "medium", "low"}

# ── Segmentation ─────────────────────────────────────────────────────


def parse_english(md: str) -> list[dict]:
    """Split the English translation into chapter sections, each a list of passages.

    Chapter boundaries are `## Preface` and the `### ` headers. The book title
    `# For Freedom!` and the stray duplicate `# Preface` are H1s inside the front
    matter / body and are NOT boundaries; page-provenance markers and any stray
    `#` lines are dropped from passage text.
    """
    lines = md.split("\n")
    starts = [i for i, l in enumerate(lines)
              if l.startswith("### ") or l.startswith("## Preface")]
    sections = []
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        title = lines[start].lstrip("#").strip()
        body = []
        for l in lines[start + 1:end]:
            if l.startswith("<!-- pages") or l.startswith("#"):
                continue
            body.append(l)
        passages = [p.strip() for p in re.split(r"\n\s*\n", "\n".join(body)) if p.strip()]
        sections.append({"title": title, "passages": passages})
    return sections


def chapter_slugs() -> list[str]:
    """Canonical slug ids (prefazione, p1_capitolo_primo, …) from the Italian text.

    P1 keys by the same scheme refine.py / typography use so stage-2 and the
    apply step can join without a second mapping.
    """
    from translate import parse_italian_markdown
    md = open(ITALIAN_MD, encoding="utf-8").read()
    return [c["id"] for c in parse_italian_markdown(md) if not c.get("is_structural")]


def build_units(only: set[str] | None = None) -> list[dict]:
    """One unit per passage: the slug-keyed target plus its neighbour context."""
    sections = parse_english(open(ENGLISH_MD, encoding="utf-8").read())
    slugs = chapter_slugs()
    if len(sections) != len(slugs):
        raise SystemExit(
            f"chapter count mismatch: {len(sections)} English sections vs "
            f"{len(slugs)} Italian slugs — alignment is positional, refusing to guess")
    units = []
    for slug, sec in zip(slugs, sections):
        if only and slug not in only:
            continue
        ps = sec["passages"]
        for i, target in enumerate(ps):
            units.append({
                "chapter": slug,
                "title": sec["title"],
                "idx": i,
                "prev": ps[i - 1] if i > 0 else None,
                "target": target,
                "next": ps[i + 1] if i + 1 < len(ps) else None,
            })
    return units


# ── Prompt ───────────────────────────────────────────────────────────

SYSTEM = """You are a COMPREHENSION reviewer for an English literary translation of a 1913 Italian memoir. You are reading ONLY the English — you do NOT have the Italian source. Judge it purely as an English reader.

You receive three passages: [PREVIOUS] and [NEXT] are context ONLY — they let you resolve pronouns, referents, and event-chains that cross paragraph boundaries. Judge ONLY the [TARGET] passage. Never raise a flag whose anchor text lives in [PREVIOUS] or [NEXT].

The translation deliberately uses an early-20th-century elevated literary register. This is INTENTIONAL. Do NOT flag a passage merely for being old-fashioned, long, periodic, formal, or ornate. Elevated style is not a defect.

Your task: find places in [TARGET] a careful reader cannot confidently make sense of on a normal read, OR that read awkwardly enough to suspect a translation glitch. For each, silently try to state its meaning in one plain sentence; flag it if any of these hold:
- you must re-read it to parse it (garden-path, tangled syntax);
- you cannot resolve who/what a pronoun or referent points to ("the latter", "he", "this", "the former");
- the chain of events or agency is unclear (who did what to whom, in what order);
- the phrasing is translationese that obscures meaning (word order or idiom that does not work in English);
- it is ungrammatical, or a word is clearly misused for the context;
- a name or term is opaque in a way that blocks understanding.

Comprehension failure is high/medium severity. Mere awkwardness you can still parse is LOW severity — include it (we want the spread), but mark it low.

OUTPUT FORMAT — record-delimited, NOT JSON. For each flag emit exactly:
@@FLAG
anchor: <a 4-to-10-word span copied VERBATIM from [TARGET] that pins the location; choose a run of words that contains NO double-quote (") characters>
sentence: <1-based index of the sentence within [TARGET] where the issue sits; best effort>
category: referent|event-chain|garden-path|translationese|grammar|opaque-term|awkward|other
severity: high|medium|low
confidence: high|medium|low
why: <plain prose: what you, as a reader, could not resolve or found awkward. May run for several lines.>
@@END

Emit one block per flag, in reading order. If [TARGET] is fully clear, output exactly the single line:
NONE
Output nothing other than @@FLAG blocks or NONE."""


def render_window(u: dict) -> str:
    def block(label, text, missing):
        return f"[{label}]\n{text if text else missing}"
    return (
        f"Chapter: {u['title']}\n\n"
        + block("PREVIOUS", u["prev"], "(none — TARGET is the first passage of the chapter)")
        + "\n\n"
        + block("TARGET", u["target"], "")
        + "\n\n"
        + block("NEXT", u["next"], "(none — TARGET is the last passage of the chapter)")
    )


# ── Model callers (return raw text + finish reason) ──────────────────


def call_claude(window: str) -> tuple[str, str]:
    import anthropic
    c = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=300)
    r = c.messages.create(model="claude-opus-4-6", max_tokens=8000, system=SYSTEM,
                          messages=[{"role": "user", "content": window}])
    raw = "".join(b.text for b in r.content if b.type == "text")
    return raw, r.stop_reason


def call_gemini(window: str) -> tuple[str, str]:
    from google import genai
    from google.genai import types
    c = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    r = c.models.generate_content(
        model="gemini-3.5-flash",
        contents=types.Content(role="user", parts=[types.Part.from_text(text=window)]),
        config=types.GenerateContentConfig(system_instruction=SYSTEM, max_output_tokens=8000))
    fr = str(r.candidates[0].finish_reason) if r.candidates else "?"
    return (r.text or ""), fr


def call_gpt(window: str) -> tuple[str, str]:
    import openai
    c = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=240)
    r = c.chat.completions.create(model="gpt-5.4", max_completion_tokens=8000,
                                  reasoning_effort=GPT_REASONING,
                                  messages=[{"role": "system", "content": SYSTEM},
                                            {"role": "user", "content": window}])
    return (r.choices[0].message.content or ""), r.choices[0].finish_reason


CALLERS = {"claude-opus-4-6": call_claude, "gemini-3.5-flash": call_gemini, "gpt-5.4": call_gpt}
# A finish reason that is NOT one of these means truncation/refusal → retry.
OK_FINISH = {"end_turn", "stop", "STOP", "FinishReason.STOP", "1"}


# ── Extraction contract ──────────────────────────────────────────────


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def resolve_anchor(anchor: str, target: str) -> int:
    """Char offset of `anchor` within `target`, accent/case/punct-insensitive.

    Returns -1 if it does not resolve. We normalise both sides and search the
    normalised target, then map back to a raw offset via a prefix-length count.
    """
    na, nt = _norm(anchor), _norm(target)
    if not na or na not in nt:
        return -1
    norm_pos = nt.find(na)
    # Map normalised position back to a raw offset by re-normalising prefixes.
    for raw_i in range(len(target) + 1):
        if len(_norm(target[:raw_i])) >= norm_pos + 1:
            return max(0, raw_i - 1)
    return 0


def parse_records(raw: str) -> tuple[list[dict] | None, str]:
    """Parse record-delimited model output.

    Returns (flags, status). status is 'ok' (clean parse, possibly empty via
    NONE), 'none' (explicit NONE), or 'malformed' (non-empty, no valid blocks
    and no NONE — caller retries). Field/enum problems inside a block downgrade
    that block's status but do not fail the whole response here; anchor
    resolution (which needs the target text) happens in the caller.
    """
    text = (raw or "").strip()
    if not text:
        return None, "malformed"
    blocks = re.findall(r"@@FLAG\b(.*?)@@END", text, re.DOTALL)
    if not blocks:
        return ([], "none") if re.search(r"\bNONE\b", text) else (None, "malformed")
    flags = []
    for b in blocks:
        rec: dict = {}
        why_lines, in_why = [], False
        for line in b.splitlines():
            if in_why:
                why_lines.append(line)
                continue
            m = re.match(r"\s*(anchor|sentence|category|severity|confidence|why)\s*:\s*(.*)$",
                         line, re.IGNORECASE)
            if not m:
                continue
            key, val = m.group(1).lower(), m.group(2).strip()
            if key == "why":
                why_lines.append(val)
                in_why = True
            else:
                rec[key] = val
        rec["why"] = "\n".join(why_lines).strip()
        try:
            rec["sentence"] = int(re.sub(r"[^0-9]", "", rec.get("sentence", "")) or 0)
        except ValueError:
            rec["sentence"] = 0
        rec["category"] = rec.get("category", "other").lower()
        if rec["category"] not in CATEGORIES:
            rec["category"] = "other"
        for lvl in ("severity", "confidence"):
            rec[lvl] = rec.get(lvl, "medium").lower()
            if rec[lvl] not in LEVELS:
                rec[lvl] = "medium"
        if rec.get("anchor"):
            flags.append(rec)
    return (flags, "ok") if flags else (None, "malformed")


def _validate(raw: str, target: str) -> dict | None:
    """Apply the extraction contract to a raw response; None if it breaches it."""
    flags, status = parse_records(raw)
    if status == "malformed":
        return None
    resolved = []
    for f in (flags or []):
        off = resolve_anchor(f["anchor"], target)
        if off < 0:
            return None        # unresolvable anchor → contract breach
        f["offset"] = off
        resolved.append(f)
    return {"status": "ok", "flags": resolved}


def review_one(unit: dict, model: str, sample: int,
               rawpath: str | None = None, resume: bool = True) -> dict:
    """One panel read of one passage, with the validated-contract retry loop.

    With resume, a previously-saved raw response that still satisfies the
    contract is reused (no API call) — making an interrupted full-book run
    cheaply restartable. A saved needs-rerun marker (`[…]`) is not reused.
    """
    window = render_window(unit)
    target = unit["target"]
    if resume and rawpath and os.path.exists(rawpath):
        cached = open(rawpath, encoding="utf-8").read()
        if not cached.lstrip().startswith("["):
            v = _validate(cached, target)
            if v is not None:
                return {**v, "raw": cached, "finish": "cached", "attempts": 0}
    last_err = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            raw, finish = CALLERS[model](window)
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:200]}"
            time.sleep(2 * attempt)
            continue
        if finish not in OK_FINISH and not raw.rstrip().endswith("@@END") \
                and "NONE" not in raw:
            last_err = f"truncated (finish={finish})"
            continue
        v = _validate(raw, target)
        if v is None:
            last_err = "unparseable / unresolvable anchor / no NONE"
            continue
        return {**v, "raw": raw, "finish": finish, "attempts": attempt}
    return {"status": "needs_rerun", "flags": [], "raw": "",
            "error": last_err, "attempts": MAX_ATTEMPTS}


# ── Scoring ──────────────────────────────────────────────────────────

SEV_RANK = {"high": 3, "medium": 2, "low": 1}
CONF_RANK = {"high": 3, "medium": 2, "low": 1}


def _overlap(a: str, b: str) -> bool:
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    wa, wb = set(a.split()), set(b.split())
    return len(wa & wb) / max(1, min(len(wa), len(wb))) >= 0.6


def cluster_and_score(flags: list[dict], samples_per_model: int) -> list[dict]:
    """Cluster a passage's flags across the panel and assign a suspicion score.

    Severity-led: breadth (distinct architectures agreeing) is the largest single
    lever, but a high-vs-low severity gap can overcome one missing architecture,
    so a passage two architectures both rate a high-severity comprehension failure
    outranks a passage three architectures merely find low-severity awkward.
    Singletons survive at a lower rank, never dropped. The component fields are
    emitted alongside the score so the weights can be retuned from the data.
    """
    clusters: list[list[dict]] = []
    for f in flags:
        for cl in clusters:
            if any(_overlap(f["anchor"], g["anchor"]) for g in cl):
                cl.append(f)
                break
        else:
            clusters.append([f])
    scored = []
    for cl in clusters:
        models = {g["_model"] for g in cl}
        breadth = len(models)
        # Strongest intra-model agreement: how many of a single model's samples
        # repeated the flag, as a fraction of that model's sample budget (capped
        # at 1.0 — a model can emit several flags into one anchor cluster).
        per_model = {m: sum(1 for g in cl if g["_model"] == m) for m in models}
        consistency = min(1.0, max(per_model.values()) / max(1, samples_per_model))
        sev = max(SEV_RANK[g["severity"]] for g in cl)
        conf = sum(CONF_RANK[g["confidence"]] for g in cl) / len(cl)
        score = round(8 * breadth + 2 * consistency + 6 * sev + 1 * conf, 2)
        rep = max(cl, key=lambda g: SEV_RANK[g["severity"]])
        scored.append({
            "score": score, "breadth": breadth,
            "consistency": round(consistency, 2), "severity_max": sev,
            "confidence_mean": round(conf, 2), "n_flags": len(cl),
            "models": sorted(models), "anchor": rep["anchor"],
            "category": rep["category"], "severity": rep["severity"],
            "offset": rep.get("offset", -1),
            "rationales": [{"model": g["_model"], "why": g["why"],
                            "category": g["category"], "severity": g["severity"],
                            "confidence": g["confidence"]} for g in cl],
        })
    return sorted(scored, key=lambda c: c["score"], reverse=True)


# ── Run ──────────────────────────────────────────────────────────────


def _rawpath(u: dict, m: str, s: int) -> str:
    return os.path.join(OUT_DIR, "raw", f"{u['chapter']}__p{u['idx']:03d}__{m}__s{s}.txt")


def run(units: list[dict], samples: int, resume: bool = True, workers: int = WORKERS) -> dict:
    os.makedirs(os.path.join(OUT_DIR, "raw"), exist_ok=True)
    tasks = [(u, m, s) for u in units for m in PANEL for s in range(samples)]
    print(f"{len(units)} passages × {len(PANEL)} models × {samples} samples "
          f"= {len(tasks)} calls; {workers} workers; resume={resume}")

    results: dict = {}   # (chapter, idx) -> {"unit":u, "reads":[...]}
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(review_one, u, m, s, _rawpath(u, m, s), resume): (u, m, s)
                for u, m, s in tasks}
        for fut in as_completed(futs):
            u, m, s = futs[fut]
            res = fut.result()
            key = (u["chapter"], u["idx"])
            slot = results.setdefault(key, {"unit": u, "reads": []})
            slot["reads"].append({"model": m, "sample": s, **res})
            open(_rawpath(u, m, s), "w", encoding="utf-8").write(
                res.get("raw", "") or f"[{res['status']}] {res.get('error', '')}")
            done += 1
            if done % 50 == 0 or done == len(tasks):
                print(f"  {done}/{len(tasks)}")

    # Per-passage clustering + scoring; collect machine flags + run health.
    ledger_rows, flat_flags = [], []
    health = {"ok": 0, "needs_rerun": 0, "none": 0}
    for (chapter, idx), slot in results.items():
        reads = slot["reads"]
        for r in reads:
            health["needs_rerun" if r["status"] == "needs_rerun" else "ok"] += 1
        ok_reads = [r for r in reads if r["status"] == "ok"]
        flags = []
        for r in ok_reads:
            for f in r["flags"]:
                flags.append({**f, "_model": r["model"]})
        if not flags:
            health["none"] += 1
            continue
        clusters = cluster_and_score(flags, samples)
        u = slot["unit"]
        for c in clusters:
            row = {"chapter": chapter, "idx": idx, "title": u["title"], **c}
            ledger_rows.append(row)
            flat_flags.append(row)

    ledger_rows.sort(key=lambda r: r["score"], reverse=True)

    # JSONL is our own serialisation (we control escaping), so it is safe here —
    # the no-JSON rule applies to MODEL output, not internal storage.
    with open(os.path.join(OUT_DIR, "flags.jsonl"), "w", encoding="utf-8") as fh:
        for row in flat_flags:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    write_ledger(ledger_rows)
    rerun = sorted(f"{m}@{ch}#{idx}"
                   for (ch, idx), slot in results.items()
                   for r in slot["reads"] if r["status"] == "needs_rerun"
                   for m in [r["model"]])
    meta = {"panel": PANEL, "samples": samples, "passages": len(results),
            "calls": len(tasks), "reads": health,
            "needs_rerun": rerun, "flag_clusters": len(ledger_rows)}
    json.dump(meta, open(os.path.join(OUT_DIR, "run_meta.json"), "w"), indent=2)
    return {"ledger": ledger_rows, "health": health, "meta": meta}


def write_ledger(rows: list[dict]) -> None:
    """Human-readable ranked suspicion ledger — the triage queue you read."""
    lines = [f"# Comprehension suspicion ledger — {len(rows)} clusters, ranked",
             "# score = 8*breadth + 2*consistency + 6*severity + 1*confidence",
             ""]
    for r in rows:
        lines.append("=" * 78)
        lines.append(f"SCORE {r['score']:6.2f}  [{r['chapter']} p{r['idx']}]  "
                     f"breadth={r['breadth']}/{len(PANEL)} consistency={r['consistency']} "
                     f"sev={r['severity']} conf={r['confidence_mean']}  "
                     f"models={','.join(m.split('-')[0] for m in r['models'])}")
        lines.append(f"  anchor: {r['anchor']}")
        lines.append(f"  category: {r['category']}")
        for rt in r["rationales"]:
            lines.append(f"  · [{rt['model'].split('-')[0]:6s} {rt['severity']:6s}/{rt['category']}] "
                         + rt["why"].replace("\n", " ").strip())
        lines.append("")
    open(os.path.join(OUT_DIR, "ledger.txt"), "w", encoding="utf-8").write("\n".join(lines))


# ── CLI ──────────────────────────────────────────────────────────────


def main() -> None:
    ap = argparse.ArgumentParser(description="P1 blind English comprehension review (collection only)")
    ap.add_argument("--chapters", help="comma-separated slug ids to limit to (default: all)")
    ap.add_argument("--samples", type=int, default=SAMPLES)
    ap.add_argument("--limit", type=int, help="cap number of passages (debugging)")
    ap.add_argument("--plan", action="store_true", help="print the task plan and exit (no API calls)")
    ap.add_argument("--fresh", action="store_true", help="ignore cached raw responses; re-call every read")
    ap.add_argument("--workers", type=int, default=WORKERS)
    args = ap.parse_args()

    only = set(args.chapters.split(",")) if args.chapters else None
    units = build_units(only)
    if args.limit:
        units = units[:args.limit]

    if args.plan:
        from collections import Counter
        by_ch = Counter(u["chapter"] for u in units)
        print(f"{len(units)} passages across {len(by_ch)} chapters")
        print(f"calls = {len(units)} × {len(PANEL)} models × {args.samples} samples "
              f"= {len(units) * len(PANEL) * args.samples}")
        for ch, n in by_ch.items():
            print(f"  {ch:28s} {n:3d}")
        return

    out = run(units, args.samples, resume=not args.fresh, workers=args.workers)
    h = out["health"]
    print(f"\nDONE  reads ok={h['ok']} needs_rerun={h['needs_rerun']}  "
          f"clean(none)-passages={h['none']}  clusters={out['meta']['flag_clusters']}")
    print(f"  ledger:  {os.path.join(OUT_DIR, 'ledger.txt')}")
    print(f"  flags:   {os.path.join(OUT_DIR, 'flags.jsonl')}")


if __name__ == "__main__":
    main()
