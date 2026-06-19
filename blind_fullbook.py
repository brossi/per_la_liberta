r"""Whole-book blind re-read as an independent deviation signal.

The reconciled-vs-final diff (diff_cleanup.py) only sees places the OCR witnesses
disagreed; it is structurally blind to errors every witness SHARED — the residue
the sampling estimate (sample_estimate.py) caught but could not localise. This
pass closes that blind spot the only honest way: read EVERY body page fresh with
the strongest reader (Gemini 3.1 Pro, native resolution) and align the
transcription against the published text to surface deviations.

The thinking-level sweep (page 230) showed `low` thinking transcribes identically
to `high` at ~1/9 the cost, with one caveat: low occasionally splits a word
across a space on a dense page. Those are FORMATTING artifacts, not reading
disagreements — `_artifact()` folds them out (published and blind read collapse
to the same letters once spaces/dashes/accents are stripped), counted but kept
off the worklist.

Output is a CANDIDATE deviation list, not ground truth: the blind read can itself
err, so each entry still needs scan-adjudication (scan_adjudicate.py) or human
audit before it is acted on — same status as the cleanup worklist pre-scan.

    uv run python blind_fullbook.py                 # all body pages (resumable)
    uv run python blind_fullbook.py --pages 19 46   # specific pages
    uv run python blind_fullbook.py --workers 8 --refresh

Output: data/blind_deviations.json  (+ per-page cache in state/blind_fullbook/)
"""

import argparse
import json
import re
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv

import sample_estimate as se
import vision_review as vr

ROOT = Path(__file__).parent
PAGES = ROOT / "data" / "chapter_pages.json"
OUT = ROOT / "data" / "blind_deviations.json"
CACHE = ROOT / "state" / "blind_fullbook"


def _alnum(s: str) -> str:
    """Lowercase, deaccented, letters/digits only — the comparison key that ignores
    spurious spaces, dashes and accent drift the blind read introduces."""
    d = "".join(c for c in unicodedata.normalize("NFD", s.lower())
                if unicodedata.category(c) != "Mn")
    return re.sub(r"[^0-9a-z]", "", d)


def _artifact(published: str, scan_blind: str) -> bool:
    """True when the only difference is spacing/dash/accent — same letters, so it is a
    blind-read formatting artifact (e.g. 'au striaca'=='austriaca'), not a misread."""
    return _alnum(published) == _alnum(scan_blind) and _alnum(published) != ""


def blind_low(pg: int) -> str:
    """Verbatim low-thinking transcription of both columns (see module note). Retry
    once on a suspiciously short read and keep the longer (chapter-opening pages are
    legitimately short, so this only helps)."""
    import os

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    img = vr.page_jpeg(pg)
    parts = [types.Part.from_text(text=f"[Copy A (LoC) scan p.{pg}]"),
             types.Part.from_bytes(data=img, mime_type="image/jpeg"),
             types.Part.from_text(text="Transcribe the full body prose of this 1913 page "
                                       "verbatim — both columns, plain text.")]

    def call() -> str:
        r = client.models.generate_content(
            model=vr.PRIMARY,
            contents=types.Content(role="user", parts=parts),
            config=types.GenerateContentConfig(
                system_instruction=se.SYSTEM_BLIND, max_output_tokens=8000,
                thinking_config=types.ThinkingConfig(thinking_level="low")))
        return se._dehyphen(r.text or "")

    best = call()
    if len(best) < 1500:
        again = call()
        if len(again) > len(best):
            best = again
    return best


def process_page(pg: int, chapters: list[dict]) -> dict:
    scan = blind_low(pg)
    published = se.chapters_for_page(chapters, pg)
    sampled, divs = se.divergences(published, scan)
    out_divs = []
    for d in divs:
        if d["kind"] != "substantive":
            continue
        d = {**d, "artifact": _artifact(d["published"], d["scan_blind"])}
        out_divs.append(d)
    return {
        "page": pg,
        "sampled_chars": sampled,
        "accent_only": sum(1 for d in divs if d["kind"] == "accent_only"),
        "substantive": out_divs,
        "blind_text": scan,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="whole-book blind re-read deviation signal")
    ap.add_argument("--pages", type=int, nargs="*", help="specific page numbers (default: all body pages)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--refresh", action="store_true", help="ignore cached page reads")
    args = ap.parse_args()
    load_dotenv(ROOT / ".env")

    chapters = se.parse_chapters()
    pages_map = json.load(open(PAGES, encoding="utf-8"))
    population = sorted({p for pgs in pages_map.values() for p in pgs})
    pages = args.pages if args.pages else population
    CACHE.mkdir(parents=True, exist_ok=True)

    todo = [p for p in pages if args.refresh or not (CACHE / f"page_{p:04d}.json").exists()]
    print(f"book body: {len(population)} pages; reading {len(todo)} this run "
          f"({len(pages) - len(todo)} cached)")

    def work(pg):
        rec = process_page(pg, chapters)
        json.dump(rec, open(CACHE / f"page_{pg:04d}.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        return rec

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for fut in as_completed([ex.submit(work, p) for p in todo]):
            rec = fut.result()
            done += 1
            real = sum(1 for d in rec["substantive"] if not d["artifact"])
            art = sum(1 for d in rec["substantive"] if d["artifact"])
            print(f"  [{done}/{len(todo)}] p.{rec['page']}: {rec['sampled_chars']} chars, "
                  f"{real} deviations, {art} artifacts")

    # Aggregate every requested page from cache.
    recs = [json.load(open(CACHE / f"page_{p:04d}.json", encoding="utf-8"))
            for p in pages if (CACHE / f"page_{p:04d}.json").exists()]
    sampled_chars = sum(r["sampled_chars"] for r in recs)
    worklist, artifacts = [], 0
    for r in recs:
        for d in r["substantive"]:
            if d["artifact"]:
                artifacts += 1
            else:
                worklist.append({"page": r["page"], "published": d["published"],
                                 "scan_blind": d["scan_blind"], "context": d["context"]})
    accent_only = sum(r["accent_only"] for r in recs)

    report = {
        "_note": "Candidate deviations from a whole-book low-thinking blind re-read aligned "
                 "against italian_clean.md. NOT ground truth — each needs scan-adjudication or "
                 "audit. 'artifacts' (spacing/dash/accent, same letters) are counted, not listed.",
        "reader": vr.PRIMARY, "thinking_level": "low",
        "pages": len(recs), "sampled_chars": sampled_chars,
        "deviations": len(worklist), "artifacts_filtered": artifacts, "accent_only": accent_only,
        "rate_per_10k": round(len(worklist) / sampled_chars * 1e4, 2) if sampled_chars else 0,
        "worklist": sorted(worklist, key=lambda w: w["page"]),
    }
    json.dump(report, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"\n{'='*64}")
    print(f"pages read: {len(recs)}   aligned chars: {sampled_chars}")
    print(f"candidate DEVIATIONS (worklist): {len(worklist)}  ({report['rate_per_10k']}/10k)")
    print(f"formatting artifacts filtered out: {artifacts}")
    print(f"accent-only differences: {accent_only}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
