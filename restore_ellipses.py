r"""Restore Crespi's period multi-dot suspension points to the Italian edition.

`cleanup.py:618` collapsed every run of 4+ dots to exactly three
(`re.sub(r"\.{4,}", "...", text)`), flattening a real early-20th-century
convention: in period Italian typesetting the dot count was not fixed, and a
longer run marked a longer/heavier pause. The pre-cleanup reconciled witness
(`data/reconciled_chapters.json`) preserves 189 four-dot runs; this restores
their counts into `output/italian_clean.md` WITHOUT re-running cleanup.

Each restored site is anchored to the derived text by the verbatim words on BOTH
sides of the ellipsis (accent/space-insensitive), so a flattened `...` is matched
to its origin even though cleanup also edited nearby words. Matching is tiered:
both-sides unique, then one-side unique among still-unused sites. The edit is
idempotent (a site already at the target count is skipped) and reversible (git).

CAVEAT: OCR dot-counts are noisy — the reconciled witness says "4" but the page
is the only authority for longer runs. This is a faithful first approximation;
scan-verification is the finalization step if the convention is kept.

    uv run python restore_ellipses.py --dry-run   # report coverage, write nothing
    uv run python restore_ellipses.py             # apply to output/italian_clean.md
"""

import argparse
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).parent
RECONCILED = ROOT / "data" / "reconciled_chapters.json"
ITALIAN = ROOT / "output" / "italian_clean.md"
ENGLISH = ROOT / "output" / "english_translation.md"
GAPS = ROOT / "data" / "ellipsis_english_gaps.json"
PAD = 48   # chars of raw context to read around a site
KEY = 24   # alnum chars used as an anchor on each side


def alnum(s):
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", (s or "").lower())
                  .encode("ascii", "ignore").decode())


def sites(text):
    """All dot-runs in `text` with their offsets and both-side alnum anchors."""
    out = []
    for m in re.finditer(r"\.{2,}", text):
        s, e = m.start(), m.end()
        before = alnum(text[max(0, s - PAD):s])[-KEY:]
        after = alnum(text[e:e + PAD])[:KEY]
        out.append({"s": s, "e": e, "n": e - s, "before": before, "after": after})
    return out


def mirror_english(dry_run):
    """Emulate the Italian: expand each English ellipsis that corresponds to an Italian
    multi-dot one. Pairing is the edition's own — chapters then paragraphs by position
    (typeset._align_chapters). Within a paragraph, ellipses map by ordinal when both
    sides have the same count (the unambiguous case); paragraphs whose counts differ
    are recorded to data/ellipsis_english_gaps.json for a manual pass rather than
    guessed at."""
    import typeset as ts
    it_text = ITALIAN.read_text(encoding="utf-8")
    en_text = ENGLISH.read_text(encoding="utf-8")
    pairs = ts._align_chapters(ts._parse_chapters(it_text), ts._parse_chapters(en_text))

    def ell(p):                       # ellipsis runs in a paragraph, in order
        # the English uses both ASCII dot-runs and the U+2026 ellipsis char; count … as 3
        out = []
        for m in re.finditer(r"\.{2,}|…+", p):
            g = m.group()
            out.append((m.start(), m.end(), len(g) if g[0] == "." else 3 * len(g)))
        return out

    # a sentence terminal that is NOT part of an ellipsis: !/? runs, or a lone period
    TERM = re.compile(r"[!?]+[\"»”’]?|(?<!\.)\.(?!\.)[\"»”’]?")
    NEAR = 0.15   # an existing English ellipsis within this paragraph-fraction is "the same" pause

    def insert_edit(en_p, frac, n):
        """Place an n-dot suspension at the sentence terminal nearest the Italian one's
        fractional position — never onto an existing dot-run (which TERM excludes)."""
        cands = list(TERM.finditer(en_p))
        if not cands:
            return None
        target = frac * len(en_p)
        c = min(cands, key=lambda m: abs(m.start() - target))
        if c.group() == ".":                           # bare period -> becomes the suspension
            return (c.start(), c.end(), "." * n)
        return (c.end(), c.end(), "." * n)             # after !/?/closing-quote -> append

    out = en_text
    cursor = 0
    expanded = inserted = considered = unplaced = unlocatable = 0
    gap_items = []
    for pair in pairs:
        its, ens = pair["italian_paragraphs"], pair["english_paragraphs"]
        for idx in range(min(len(its), len(ens))):
            it_p, en_p = its[idx], ens[idx]
            it_ell, en_ell = ell(it_p), ell(en_p)
            multidot = [k for k, (_, _, n) in enumerate(it_ell) if n >= 4]
            if not multidot:
                continue
            considered += len(multidot)
            pos = out.find(en_p, cursor)        # locate paragraph in file, document order
            if pos == -1:
                unlocatable += len(multidot)
                continue
            cursor = pos + len(en_p)
            en_frac = [((s + e) / 2) / max(1, len(en_p)) for s, e, _ in en_ell]
            used = set()
            ins_used = set()
            edits = []
            for k in multidot:
                s, e, target = it_ell[k]
                f = ((s + e) / 2) / max(1, len(it_p))
                near = sorted((j for j in range(len(en_ell)) if j not in used),
                              key=lambda j: abs(en_frac[j] - f))
                if near and abs(en_frac[near[0]] - f) <= NEAR:   # expand the matching ellipsis
                    j = near[0]
                    used.add(j)
                    es, ee, en_n = en_ell[j]
                    if en_n != target:
                        edits.append((es, ee, "." * target, "expand"))
                    continue
                ed = insert_edit(en_p, f, target)               # no nearby ellipsis -> insert
                # skip if a prior multi-dot already claimed this terminal (avoids 4+4 stacking)
                placed = bool(ed) and ed[0] not in ins_used
                gap_items.append({"chapter": pair["english_title"], "paragraph": idx,
                                  "it_dots": target, "placed": placed,
                                  "italian": it_p[max(0, s - 60):e + 3], "english": en_p[:220]})
                if placed:
                    ins_used.add(ed[0])
                    edits.append((ed[0], ed[1], ed[2], "insert"))
                elif not ed:
                    unplaced += 1
            new_en = en_p
            for es, ee, repl, kind in sorted(edits, key=lambda x: -x[0]):
                new_en = new_en[:es] + repl + new_en[ee:]
                if kind == "expand":
                    expanded += 1
                else:
                    inserted += 1
            if new_en != en_p:
                out = out[:pos] + new_en + out[pos + len(en_p):]
                cursor = pos + len(new_en)

    print(f"english: italian multi-dot ellipses considered: {considered}")
    print(f"  expanded an existing english ellipsis: {expanded}")
    print(f"  inserted a suspension (no english ellipsis, estimated placement): {inserted}")
    print(f"  could not place (no sentence terminal found): {unplaced}")
    print(f"  unlocatable paragraphs (page-marker splits): {unlocatable}")
    if not dry_run:
        ENGLISH.write_text(out, encoding="utf-8")
        GAPS.write_text(json.dumps({"_note": "English spots where no ellipsis existed, so a "
                                    "suspension was INSERTED at an estimated sentence boundary "
                                    "to mirror the Italian. Review placement when finishing cleanup.",
                                    "items": gap_items}, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        print(f"\nwrote {ENGLISH}\nwrote {GAPS}")
    else:
        print("\n--dry-run: output/english_translation.md unchanged")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--english", action="store_true",
                    help="mirror restored Italian multi-dot ellipses into the English")
    args = ap.parse_args()
    if args.english:
        mirror_english(args.dry_run)
        return

    rec = json.loads(RECONCILED.read_text(encoding="utf-8"))
    italian = ITALIAN.read_text(encoding="utf-8")
    dsites = sites(italian)
    used = set()

    # reconciled multi-dot (4+) targets, with both-side anchors
    targets = []
    for ch in rec:
        t = ch["text"]
        for m in re.finditer(r"\.{4,}", t):
            s, e = m.start(), m.end()
            targets.append({"chapter": ch["id"], "n": e - s,
                            "before": alnum(t[max(0, s - PAD):s])[-KEY:],
                            "after": alnum(t[e:e + PAD])[:KEY]})

    def pick(tgt):
        """Return the unique unused derived site for this target, or None."""
        b, a = tgt["before"], tgt["after"]
        if len(b) < 8 and len(a) < 8:
            return None
        both = [i for i, d in enumerate(dsites)
                if i not in used and d["before"] == b and d["after"] == a]
        if len(both) == 1:
            return both[0]
        if both:                       # multiple both-side matches: ambiguous
            return None
        bonly = [i for i, d in enumerate(dsites) if i not in used and d["before"] == b]
        if len(bonly) == 1:
            return bonly[0]
        aonly = [i for i, d in enumerate(dsites) if i not in used and d["after"] == a]
        if len(aonly) == 1:
            return aonly[0]
        return None

    edits = []          # (site_index, new_count)
    resolved = already = unresolved = 0
    for tgt in targets:
        i = pick(tgt)
        if i is None:
            unresolved += 1
            continue
        used.add(i)
        resolved += 1
        if dsites[i]["n"] == tgt["n"]:
            already += 1
        else:
            edits.append((i, tgt["n"]))

    print(f"reconciled multi-dot targets: {len(targets)}")
    print(f"  resolved to a derived site: {resolved}")
    print(f"    already correct (idempotent skip): {already}")
    print(f"    to restore: {len(edits)}")
    print(f"  unresolved (anchor not unique): {unresolved}")

    if args.dry_run:
        print("\n--dry-run: output/italian_clean.md unchanged")
        return

    # apply from the end so earlier offsets stay valid
    out = italian
    for i, n in sorted(edits, key=lambda x: -dsites[x[0]]["s"]):
        d = dsites[i]
        out = out[:d["s"]] + ("." * n) + out[d["e"]:]
    ITALIAN.write_text(out, encoding="utf-8")
    after_counts = {}
    for d in sites(out):
        after_counts[d["n"]] = after_counts.get(d["n"], 0) + 1
    print(f"\nwrote {ITALIAN}")
    print(f"dot-run distribution now: {dict(sorted(after_counts.items()))}")


if __name__ == "__main__":
    main()
