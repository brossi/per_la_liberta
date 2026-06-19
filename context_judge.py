r"""Context judge for the cleanup-corruption worklist.

`diff_cleanup.py` flags every place cleanup changed a word whose pre-cleanup
form is a real period word (632 candidates). But dictionary membership can't
tell DIRECTION: OCR garble often forms real words too (`nielo`->`cielo` is a
legitimate fix, not a corruption). This judge reads each sentence and decides
which reading the 1913 author most likely wrote — collapsing the candidates to a
high-precision worklist for the human scan-audit.

It is a TEXT-only heuristic filter (no scans), not ground truth: the scan-audit
remains the arbiter. Period/archaic spelling and enclitics are CORRECT for 1913
and must be preferred (boja not boia, eclissarne not eclissare) — see the
fidelity-errors principle. Reader is Claude Sonnet 4.6.

    uv run python context_judge.py            # judge all candidates
    uv run python context_judge.py --limit 40 # smoke test

Output: data/cleanup_worklist_judged.json
  verdict "source" = pre-cleanup reading is right => CORRUPTION (keep for audit)
  verdict "final"  = cleaned reading is right     => legitimate fix (drop)
  verdict "unsure" = keep for audit, low priority
"""

import argparse
import concurrent.futures as cf
import json
import os
import re
import unicodedata
from pathlib import Path

from dotenv import load_dotenv

import diff_cleanup as dc

ROOT = Path(__file__).parent
CANDS = ROOT / "data" / "cleanup_corruption_candidates.json"
OUT = ROOT / "data" / "cleanup_worklist_judged.json"
MODEL = "claude-sonnet-4-6"
BATCH = 20

CLITICS = dc.CLITICS


def deacc(s):
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def signature(A, B):
    a, b = deacc(A), deacc(B)
    for c in CLITICS:
        if a.endswith(c) and len(a) - len(c) >= 3:
            stem = a[:-len(c)]
            if b == stem or b == stem + "e" or (b.endswith(tuple(CLITICS)) and b.startswith(stem)):
                return "clitic"
    if "j" in A.lower() and a.replace("j", "i") == b.replace("j", "i"):
        return "archaic_j"
    if abs(len(a) - len(b)) == 1:
        long, short = (a, b) if len(a) > len(b) else (b, a)
        for i in range(len(short)):
            if long[i] != short[i]:
                if i > 0 and long[i] == long[i - 1]:
                    return "gemination"
                break
        else:
            if len(long) > 1 and long[-1] == long[-2]:
                return "gemination"
    return ""


def neutral_ctx(tokens, idx, width=10):
    lo, hi = max(0, idx - width), min(len(tokens), idx + width + 1)
    return " ".join(tokens[lo:idx] + ["___"] + tokens[idx + 1:hi])


def build_final_contexts():
    """Re-align reconciled vs final (difflib only, no dict calls) to map each
    1:1 substitution to a clean final-text sentence with the slot blanked."""
    import difflib
    rec = {c["id"]: c for c in json.loads(dc.RECON.read_text(encoding="utf-8"))}
    ranges, bodies = dc.final_bodies()
    fmap = {}
    for cid, body in zip(dc.IDS, bodies):
        if cid not in rec:
            continue
        a = dc.TOKEN.findall(rec[cid]["text"])
        b = dc.TOKEN.findall(body)
        sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "replace" and (i2 - i1) == 1 and (j2 - j1) == 1:
                fmap[(cid, a[i1], b[j1], dc.context(a, i1, a[i1]))] = neutral_ctx(b, j1)
    return fmap


SYSTEM = (
    "You are an expert philologist of early-20th-century Italian, auditing the "
    "OCR-then-automated-cleanup of a 1913 Italian book (Cesare Crespi, Risorgimento "
    "memoir). For each item you get a sentence with one word blanked as ___ and two "
    "candidate readings: SOURCE (the original scan's OCR, before automated cleanup) "
    "and FINAL (after a dictionary/LLM cleanup that sometimes WRONGLY modernized or "
    "mis-'corrected' a valid word).\n\n"
    "Decide which reading the 1913 author most likely wrote.\n"
    "CRITICAL RULES:\n"
    "- Period and archaic spelling and elisions are CORRECT for 1913 and must be "
    "preferred over modern forms: e.g. prefer 'boja' over 'boia', 'patriotti' over "
    "'patrioti', enclitic 'eclissarne' over 'eclissare', \"coll'armi\" over 'colle "
    "armi'.\n"
    "- Prefer SOURCE whenever it is a valid (even archaic/literary/dialectal) Italian "
    "word that fits the sentence grammatically and in meaning.\n"
    "- Prefer FINAL only when SOURCE is clearly OCR garble that is not the right word "
    "here (e.g. 'nielo' for 'cielo', 'ritomo' for 'ritorno', 'Piglia' for 'Figlia').\n"
    "- If both are plausible and you cannot decide, use 'unsure'.\n\n"
    "Reply with ONLY a JSON array, one object per item: "
    '{"id": <int>, "verdict": "source"|"final"|"unsure", "reason": "<concise>"}'
)


def judge_batch(items):
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=180)
    payload = [{"id": it["id"], "sentence": it["sentence"],
                "SOURCE": it["source"], "FINAL": it["final"]} for it in items]
    last = None
    for _ in range(3):
        msg = client.messages.create(
            model=MODEL, max_tokens=4000, system=SYSTEM,
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        )
        text = "".join(b.text for b in msg.content if b.type == "text")
        m = re.search(r"\[.*\]", text, re.S)  # tolerate prose around the JSON array
        if m:
            try:
                return {r["id"]: r for r in json.loads(m.group(0))}
            except json.JSONDecodeError as e:
                last = e
    raise last or ValueError("no JSON array in response")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    load_dotenv()

    cands = json.loads(CANDS.read_text(encoding="utf-8"))["items"]
    fmap = build_final_contexts()

    items = []
    for i, c in enumerate(cands):
        key = (c["chapter"], c["source"], c["final"], c["context"])
        items.append({
            "id": i, "chapter": c["chapter"], "pages": c["pages"],
            "source": c["source"], "final": c["final"],
            "confidence": c["confidence"], "evidence": c["evidence"],
            "signature": signature(c["source"], c["final"]),
            "sentence": fmap.get(key, c["context"].replace(f"⟦{c['source']}⟧", "___")),
        })
    if args.limit:
        items = items[:args.limit]

    batches = [items[i:i + BATCH] for i in range(0, len(items), BATCH)]
    print(f"judging {len(items)} candidates in {len(batches)} batches...")
    verdicts = {}
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(judge_batch, b): bi for bi, b in enumerate(batches)}
        for fut in cf.as_completed(futs):
            try:
                verdicts.update(fut.result())
            except Exception as e:
                print(f"  batch {futs[fut]} failed: {e}")

    for it in items:
        v = verdicts.get(it["id"], {})
        it["verdict"] = v.get("verdict", "unsure")
        it["reason"] = v.get("reason", "(no verdict)")

    from collections import Counter
    vc = Counter(it["verdict"] for it in items)
    corruptions = [it for it in items if it["verdict"] == "source"]
    report = {
        "_note": "Context-judged cleanup worklist. verdict 'source' = corruption (audit); "
                 "'final' = legitimate fix (drop); 'unsure' = audit, low priority.",
        "model": MODEL, "judged": len(items), "verdict_counts": dict(vc),
        "worklist": [it for it in items if it["verdict"] in ("source", "unsure")],
        "dropped_legit_fixes": [it for it in items if it["verdict"] == "final"],
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nverdicts: {dict(vc)}")
    print(f"WORKLIST (corruptions + unsure): {len(report['worklist'])}  "
          f"(confirmed corruptions: {len(corruptions)})")
    print(f"dropped as legit fixes: {vc['final']}")
    print(f"wrote {OUT}\n")
    print("sample confirmed corruptions:")
    for it in corruptions[:15]:
        print(f"  [{it.get('signature') or '-':>9}|{it['confidence']:>6}] {it['source']!r} -> {it['final']!r}  ({it['reason'][:50]})")
    print("\nsample dropped (legit fixes):")
    for it in items:
        if it["verdict"] == "final":
            print(f"  {it['source']!r} -> {it['final']!r}  ({it['reason'][:50]})")
            if len([x for x in items[:items.index(it)+1] if x['verdict']=='final']) >= 10:
                break


if __name__ == "__main__":
    main()
