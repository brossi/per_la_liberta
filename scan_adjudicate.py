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
# Whole-book blind-read deviation worklist (blind_fullbook.py) — same adjudication,
# different source: SOURCE=the fresh blind read, FINAL=the shipped published text.
BLIND_WORKLIST = ROOT / "data" / "blind_deviations.json"
OUT_BLIND = ROOT / "data" / "blind_deviations_scanned.json"
CACHE_BLIND = ROOT / "state" / "scan_adjudication_blind"
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


def _ask(images, queries, thinking=None):
    payload = [{"id": q["id"], "sentence": q["sentence"],
                "SOURCE": q["source"], "FINAL": q["final"]} for q in queries]
    user = json.dumps(payload, ensure_ascii=False)
    for _ in range(2):
        parsed, _raw = vr.read_json_images(images, SYSTEM, user, thinking=thinking)
        if isinstance(parsed, list):
            return {r["id"]: r for r in parsed if "id" in r}
    return {}


def adjudicate_chapter(ch, items, cache_dir, thinking=None, refresh=False):
    cache = cache_dir / f"{ch}.json"
    if cache.exists() and not refresh:
        return json.loads(cache.read_text(encoding="utf-8"))

    # Union of every item's page(s): one page each for blind items, the whole chapter
    # range for cleanup items (all share it) — so this is correct for both sources.
    pages = sorted({p for it in items
                    for p in range(span(it["pages"])[0], span(it["pages"])[1] + 1)})
    pending = {it["id"]: it for it in items}
    results = {}

    def run(label_fn, page_list, copy, by_page):
        for batch in chunks(page_list, PAGE_BATCH):
            if not pending:
                return
            # On Copy A the item page IS a LoC page, so ask only the items whose page is
            # in this batch — fewer items per call avoids JSON truncation and the model
            # reporting found=false for sentences that aren't on the shown pages. On Copy
            # B the page numbering differs (Harvard), so fall back to asking all pending.
            if by_page:
                bs = set(batch)
                q = [it for it in pending.values()
                     if bs & set(range(span(it["pages"])[0], span(it["pages"])[1] + 1))]
            else:
                q = list(pending.values())
            if not q:
                continue
            try:
                imgs = [label_fn(p) for p in batch]
            except Exception:
                continue
            verdicts = _ask(imgs, q, thinking=thinking)
            for vid, v in verdicts.items():
                if v.get("found"):
                    it = pending.pop(vid, None)
                    if it:
                        results[vid] = {**it, "scan_printed": v.get("printed"),
                                        "scan_text": v.get("printed_text", ""),
                                        "scan_confidence": v.get("confidence", ""),
                                        "scan_copy": copy, "scan_pages": batch}

    run(lambda p: (f"Copy A (LoC) scan p.{p}", vr.page_jpeg(p)), pages, "A", by_page=True)
    if pending:
        hpages = vr.harvard_window(pages)
        run(lambda h: (f"Copy B (Harvard) scan p.{h}", vr.harvard_jpeg(h)), hpages, "B", by_page=False)
    for vid, it in pending.items():
        results[vid] = {**it, "scan_printed": "not_found", "scan_text": "",
                        "scan_confidence": "", "scan_copy": "", "scan_pages": []}

    out = list(results.values())
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def _load_blind():
    """Normalise the blind-read deviation worklist into the common item shape. SOURCE is
    the fresh blind read (the candidate restoration), FINAL the shipped published text;
    each item is pinned to its single page, grouped by chapter via chapter_pages.json."""
    raw = json.loads(BLIND_WORKLIST.read_text(encoding="utf-8"))["worklist"]
    pages_map = json.loads((ROOT / "data" / "chapter_pages.json").read_text(encoding="utf-8"))
    page2ch = {}
    for ch, pgs in pages_map.items():
        for p in pgs:
            page2ch.setdefault(int(p), ch)
    wl = []
    for i, d in enumerate(raw):
        pg = int(d["page"])
        wl.append({"id": i, "chapter": page2ch.get(pg, f"page_{pg}"),
                   "pages": f"{pg}-{pg}", "source": d["scan_blind"],
                   "final": d["published"], "sentence": d.get("context", ""), "page": pg})
    return wl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["cleanup", "blind"], default="cleanup",
                    help="which worklist to adjudicate against the scans")
    ap.add_argument("--thinking", default="medium",
                    help="Gemini thinking_level: low|medium|high, or 'none' for model default")
    ap.add_argument("--chapter", help="adjudicate a single chapter id")
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    thinking = None if args.thinking == "none" else args.thinking

    if args.source == "blind":
        wl = _load_blind()
        out_path, cache_dir = OUT_BLIND, CACHE_BLIND
        note = ("Scan-adjudicated whole-book blind-read deviations. scan_printed: "
                "source=page shows the blind read (published is WRONG — adopt source), "
                "final=page shows published (blind read erred — false alarm), "
                "other=third reading in scan_text, not_found=needs manual location.")
    else:
        wl = json.loads(WORKLIST.read_text(encoding="utf-8"))["worklist"]
        out_path, cache_dir = OUT, CACHE
        note = ("Scan-adjudicated worklist. scan_printed: source=corruption confirmed "
                "(restore source), final=false alarm (keep final), other=true reading in "
                "scan_text, not_found=needs manual location.")
    cache_dir.mkdir(parents=True, exist_ok=True)

    bych = defaultdict(list)
    for it in wl:
        bych[it["chapter"]].append(it)
    if args.chapter:
        bych = {args.chapter: bych[args.chapter]}

    print(f"scan-adjudicating {sum(len(v) for v in bych.values())} candidates "
          f"across {len(bych)} chapters (source={args.source}, thinking={args.thinking})...")
    records = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(adjudicate_chapter, ch, items, cache_dir, thinking, args.refresh): ch
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
        "_note": note,
        "reader": vr.PRIMARY, "thinking": args.thinking, "judged": len(records),
        "scan_printed_counts": dict(pc),
        "items": sorted(records, key=lambda r: (str(r["chapter"]), -1 if r["scan_printed"] == "source" else 0)),
    }
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nscan verdicts: {dict(pc)}")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
