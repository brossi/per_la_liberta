r"""Verify each blind-read 'dittography' against the derived text.

The structural rule in `classify_deviations.py` tags a deviation as dittography
whenever the page-read slot is empty but the published slot has text — but that
shape is produced equally by a genuine edition duplication AND by a blind-read
OMISSION that left a phantom alignment slot. Only the derived text settles it:
a real dittography shows the published fragment duplicated ADJACENTLY in
`output/italian_clean.md`; a phantom does not appear duplicated at all.

For each dittography item we locate its paragraph in the derived text (scored by
shared distinctive words, so short fragments like 'io' don't match elsewhere in
the book), then test whether the published token sequence occurs twice with only
punctuation/space between. Items with no adjacent duplication are marked
`suggest_flag` — the sheet stars the ⚑ Flag button so they come pre-flagged as
likely false findings (the human still confirms).

    uv run python verify_dittography.py            # patch classified JSON in place
    uv run python verify_dittography.py --dry-run  # report only

Writes `dup_real` / `suggest_flag` / refined `reason` onto the dittography items
of data/blind_deviations_classified.json.
"""

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).parent
CLASSIFIED = ROOT / "data" / "blind_deviations_classified.json"
DERIVED = ROOT / "output" / "italian_clean.md"


def words(s):
    return re.findall(r"[A-Za-zÀ-ÿ']+", s or "")


def adjacent_dup(flat, frag, sentence):
    """Is the published fragment duplicated adjacently at its location in the derived text?

    Anchor to the occurrence of the fragment whose surrounding text best matches the
    blind sentence (so single-word fragments like 'io' don't false-match elsewhere in
    the book), then test for an adjacent repeat in a tight window around it."""
    seq = words(frag)
    if not seq:
        return False
    pat = r"\W+".join(re.escape(w) for w in seq)
    occ = list(re.finditer(pat, flat, re.I))
    if not occ:
        return False
    keys = {w.lower() for w in words(sentence) if len(w) >= 5}

    def score(m):
        w = flat[max(0, m.start() - 80):m.end() + 80].lower()
        return sum(1 for k in keys if k in w)

    best = max(occ, key=score)
    L = best.end() - best.start()
    win = flat[max(0, best.start() - L - 12):best.end() + L + 12]
    return bool(re.search(r"(?<!\w)(" + pat + r")(\W{0,6})(" + pat + r")(?!\w)", win, re.I))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    report = json.loads(CLASSIFIED.read_text(encoding="utf-8"))
    derived = DERIVED.read_text(encoding="utf-8")
    flat = re.sub(r"\s+", " ", derived)

    real, phantom = [], []
    for it in report["items"]:
        if it.get("category") != "dittography":
            continue
        frag = it.get("published", "")
        dup = adjacent_dup(flat, frag, it.get("sentence", ""))
        it["dup_real"] = dup
        it["suggest_flag"] = not dup
        if dup:
            real.append(it["id"])
            it["reason"] = "duplicated in the derived text — real; remove the repeat or keep if intentional"
        else:
            phantom.append(it["id"])
            it["reason"] = "no duplication in the derived text — likely a blind-read artifact, not a real deviation"

    print(f"dittography items: {len(real) + len(phantom)}")
    print(f"  REAL (duplicated in derived):    {sorted(real)}")
    print(f"  PHANTOM (suggest flag):          {sorted(phantom)}")
    if args.dry_run:
        print("\n--dry-run: no file written")
        return
    CLASSIFIED.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {CLASSIFIED}")


if __name__ == "__main__":
    main()
