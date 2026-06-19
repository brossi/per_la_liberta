r"""Scan-adjudicate the cleanup-corruption worklist against the 1913 source pages.

`context_judge.py` filters the diff candidates to 235 probable corruptions using
text fluency alone — no access to the page. This pass settles each against
GROUND TRUTH: Gemini 3.1 Pro reads the actual scan and reports which spelling is
printed (the established vision reviewer + native-resolution rule, escalating to
the second physical copy via the concordance — see vision_review.py).

Per chapter: read its Copy A (LoC) pages in small batches, locate each
candidate's sentence, report printed = source | final | other:
  source = the pre-cleanup reading is on the page  -> CORRUPTION confirmed (restore it)
  final  = the cleaned reading is on the page       -> false alarm (cleanup was right)
  other  = neither; printed_text holds the true reading
Candidates not located / low-confidence on Copy A escalate to Copy B (Harvard).

This produces scan evidence to PRE-FILL the audit sheet; the human remains the
arbiter (confirms/overturns each), per the human-validation principle.

    uv run python scan_adjudicate.py                 # all chapters
    uv run python scan_adjudicate.py --chapter p1_ch06   # one chapter
    uv run python scan_adjudicate.py --workers 5 --refresh

Output: data/cleanup_worklist_scanned.json  (+ per-chapter cache in state/scan_adjudication/)
"""

import argparse
import concurrent.futures as cf
import json
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

import vision_review as vr

load_dotenv()

ROOT = Path(__file__).parent
WORKLIST = ROOT / "data" / "cleanup_worklist_judged.json"
OUT = ROOT / "data" / "cleanup_worklist_scanned.json"
CACHE = ROOT / "state" / "scan_adjudication"
PAGE_BATCH = 3

SYSTEM = (
    "You are reading native-resolution scans of page(s) from a 1913 Italian book "
    "(two-column body). For each query you get a sentence with one word shown as "
    "___ and two candidate spellings, SOURCE and FINAL. Locate that exact sentence "
    "on the page image(s) and report which spelling is ACTUALLY PRINTED, letter for "
    "letter. The 1913 printing uses period/archaic spelling and elisions (e.g. "
    "'boja', 'patriotti', \"coll'armi\", enclitics like 'eclissarne') — transcribe "
    "exactly what is printed, including such forms; do NOT modernize. If the printed "
    "word matches neither candidate, use 'other' and give the exact printed word. If "
    "you cannot find the sentence on these page(s), set found=false.\n"
    "Reply with ONLY a JSON array: "
    '[{"id":int,"found":bool,"printed":"source"|"final"|"other",'
    '"printed_text":"<exact word as printed>","confidence":"high"|"medium"|"low"}]'
)


def span(p):
    a = p.split("-")
    return int(a[0]), int(a[-1])


def chunks(xs, n):
    return [xs[i:i + n] for i in range(0, len(xs), n)]


def _ask(images, queries):
    payload = [{"id": q["id"], "sentence": q["sentence"],
                "SOURCE": q["source"], "FINAL": q["final"]} for q in queries]
    user = json.dumps(payload, ensure_ascii=False)
    for _ in range(2):
        parsed, _raw = vr.read_json_images(images, SYSTEM, user)
        if isinstance(parsed, list):
            return {r["id"]: r for r in parsed if "id" in r}
    return {}


def adjudicate_chapter(ch, items, refresh=False):
    cache = CACHE / f"{ch}.json"
    if cache.exists() and not refresh:
        return json.loads(cache.read_text(encoding="utf-8"))

    lo, hi = span(items[0]["pages"])
    pages = list(range(lo, hi + 1))
    pending = {it["id"]: it for it in items}
    results = {}

    def run(label_fn, page_list, copy):
        for batch in chunks(page_list, PAGE_BATCH):
            if not pending:
                return
            try:
                imgs = [label_fn(p) for p in batch]
            except Exception:
                continue
            verdicts = _ask(imgs, list(pending.values()))
            for vid, v in verdicts.items():
                if v.get("found"):
                    it = pending.pop(vid, None)
                    if it:
                        results[vid] = {**it, "scan_printed": v.get("printed"),
                                        "scan_text": v.get("printed_text", ""),
                                        "scan_confidence": v.get("confidence", ""),
                                        "scan_copy": copy, "scan_pages": batch}

    run(lambda p: (f"Copy A (LoC) scan p.{p}", vr.page_jpeg(p)), pages, "A")
    if pending:
        hpages = vr.harvard_window(pages)
        run(lambda h: (f"Copy B (Harvard) scan p.{h}", vr.harvard_jpeg(h)), hpages, "B")
    for vid, it in pending.items():
        results[vid] = {**it, "scan_printed": "not_found", "scan_text": "",
                        "scan_confidence": "", "scan_copy": "", "scan_pages": []}

    out = list(results.values())
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chapter", help="adjudicate a single chapter id")
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    wl = json.loads(WORKLIST.read_text(encoding="utf-8"))["worklist"]
    bych = defaultdict(list)
    for it in wl:
        bych[it["chapter"]].append(it)
    if args.chapter:
        bych = {args.chapter: bych[args.chapter]}

    print(f"scan-adjudicating {sum(len(v) for v in bych.values())} candidates "
          f"across {len(bych)} chapters...")
    records = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(adjudicate_chapter, ch, items, args.refresh): ch
                for ch, items in bych.items()}
        for fut in cf.as_completed(futs):
            ch = futs[fut]
            try:
                recs = fut.result()
                records.extend(recs)
                conf = sum(1 for r in recs if r["scan_printed"] == "source")
                print(f"  {ch}: {len(recs)} done ({conf} confirm source)")
            except Exception as e:
                print(f"  {ch}: FAILED {e}")

    from collections import Counter
    pc = Counter(r["scan_printed"] for r in records)
    report = {
        "_note": "Scan-adjudicated worklist. scan_printed: source=corruption confirmed "
                 "(restore source), final=false alarm (keep final), other=true reading in "
                 "scan_text, not_found=needs manual location.",
        "reader": vr.PRIMARY, "judged": len(records), "scan_printed_counts": dict(pc),
        "items": sorted(records, key=lambda r: (r["chapter"], -1 if r["scan_printed"] == "source" else 0)),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nscan verdicts: {dict(pc)}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
