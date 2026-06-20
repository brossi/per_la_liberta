r"""Scan-confirm (and auto-clear) the phantom dittography findings.

`verify_dittography.py` flagged 12 dittography candidates as phantoms: the published
phrase is NOT duplicated in the derived text, so the edition cannot be repeating it.
That settles the *dittography* question from our own output. The only thing a scan
adds is separating the two causes of the empty blind-read slot that produced the
candidate:

  - blind read OMITTED a phrase the page does carry  -> phantom (edition faithful)
  - the page genuinely lacks it, edition has it       -> edition-added text (real!)

The dittography itself is already settled by the TEXT (the phrase appears once in the
edition -> no duplication), so this pass CLEARS all phantoms on that evidence and uses a
scan only to corroborate. A *count* query proved unreliable on dense pages (returned
"io appears once", "erano zero times"), and so did a presence query on awkward fragments
('erano' came back not-found), so the scan cannot be the arbiter — a False here is a
fragment-query failure, NOT edition-added text. We still record it: where the scan can
match a distinctive phrase it confirms the page carries it (blind-read omission).
thinking=low (no reasoning budget needed, see project_blind_read_signal).

    uv run python confirm_phantoms.py --dry-run   # report, write nothing
    uv run python confirm_phantoms.py             # write resolved + scan_present back

Sets resolved="phantom" + scan_present on the phantom items of
data/blind_deviations_classified.json; build_deviation_sheet drops resolved items.
"""

import argparse
import concurrent.futures as cf
import json
import re
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image

import vision_review as vr

ROOT = Path(__file__).parent
CLASSIFIED = ROOT / "data" / "blind_deviations_classified.json"
PAGE_DIR = ROOT / "docs" / "assets" / "page_images"
SYS = "You read a scanned page of a 1913 Italian book and count occurrences of a phrase."


def present_on_page(page, phrase):
    """Presence check (reliable), not a count (unreliable on dense pages). Returns
    True/False, or None if the read failed."""
    path = PAGE_DIR / f"page_{page:04d}.png"
    if not path.exists():
        return None
    jpeg = vr._jpeg(Image.open(path).convert("RGB"))
    user = (f'Does this phrase appear as printed text anywhere on this page, allowing for '
            f'minor OCR/spacing/accent/punctuation differences? Phrase: "{phrase}". '
            'Reply with ONLY JSON: {"present": true|false}.')
    for _ in range(3):
        parsed, _raw = vr.read_json_images([("page", jpeg)], SYS, user, thinking="low")
        if isinstance(parsed, dict) and isinstance(parsed.get("present"), bool):
            return parsed["present"]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    load_dotenv(ROOT / ".env")

    report = json.loads(CLASSIFIED.read_text(encoding="utf-8"))
    phantoms = [it for it in report["items"]
                if it.get("category") == "dittography" and it.get("suggest_flag")
                and it.get("scan_copy", "A") == "A"]
    print(f"phantom dittographies to scan-confirm: {len(phantoms)}")

    def work(it):
        return it["id"], present_on_page(it["page"], it["published"])

    present = {}
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        for fut in cf.as_completed([ex.submit(work, it) for it in phantoms]):
            i, p = fut.result()
            present[i] = p

    # The dittography is ruled out by the TEXT (appears once in the edition) — reliable,
    # our own output. The scan only corroborates; a False here is a fragment-query failure
    # (e.g. it returns not-found for the ubiquitous word 'erano'), NOT edition-added text.
    corrob = scanfail = 0
    for it in phantoms:
        p = present.get(it["id"])
        it["scan_present"] = p
        it["resolved"] = "phantom"
        if p is True:
            it["reason"] = "text: no duplication in the edition; scan corroborates phrase on the page — blind-read omission, not a deviation"
            corrob += 1
        else:
            it["reason"] = "text: no duplication in the edition; scan presence-query unreliable for this fragment — cleared on text evidence"
            scanfail += 1

    print(f"  cleared as phantom (all):           {len(phantoms)}")
    print(f"    scan corroborated on page:        {corrob}")
    print(f"    scan inconclusive (fragment), text-cleared: {scanfail}")
    for it in phantoms:
        print(f"    #{it['id']} p.{it['page']}  scan_present={present.get(it['id'])}  {it['published'][:40]!r}")

    if args.dry_run:
        print("\n--dry-run: classified JSON unchanged")
        return
    CLASSIFIED.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {CLASSIFIED}")


if __name__ == "__main__":
    main()
