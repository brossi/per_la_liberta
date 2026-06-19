r"""Classify the scan-confirmed blind-read deviations into ACTION categories.

`scan_adjudicate.py --source blind` settles whether the page prints the published
text or something else, but its source/final/other scheme conflates two opposite
situations under "source":

  - published wrongly MODERNIZED a valid 1913 form (boja->boia)         -> RESTORE page
  - published correctly FIXED a 1913 printer's typo  (Meternich->       -> KEEP published
    Metternich)

Restoring the second class would re-introduce printer errors into the edition.
This pass re-classifies each confirmed deviation. It needs no scan re-read: the
printed form (scan_text) is already ground truth from the adjudication, so this is
a TEXT judgement about the RELATIONSHIP between printed and published, informed by
the three period dictionaries and the model's world knowledge. It is triage — the
boxed-word review sheet remains the human arbiter.

Structural cases are tagged without the model:
  - published empty  -> omission   (page has a word the edition dropped) -> restore
  - printed  empty   -> dittography(edition repeats; page does not)      -> review

    uv run python classify_deviations.py            # all confirmed
    uv run python classify_deviations.py --limit 40 # smoke test

Output: data/blind_deviations_classified.json
"""

import argparse
import concurrent.futures as cf
import functools
import json
import os
import re
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent
SCANNED = ROOT / "data" / "blind_deviations_scanned.json"
OUT = ROOT / "data" / "blind_deviations_classified.json"
MODEL = "claude-sonnet-4-6"
BATCH = 20

SYSTEM = (
    "You are an expert philologist of early-20th-century Italian, triaging deviations "
    "between the PRINTED text of a 1913 Italian book (Cesare Crespi) and its modern "
    "PUBLISHED transcription. For each item you get the word actually PRINTED on the "
    "1913 page (ground truth, read from the scan), the PUBLISHED word, the sentence, and "
    "how many of three period dictionaries (Zingarelli 1922, Edgren 1901, Hoare 1915) "
    "recognise each form (0-3).\n\n"
    "Classify the RELATIONSHIP and choose an ACTION:\n"
    "- \"modernization\": PRINTED is a valid period/archaic/dialectal spelling or elision "
    "and PUBLISHED modernised it (boja/boia, patriotti/patrioti, riescirono/riuscirono, "
    "coll'armi/colle armi). ACTION restore.\n"
    "- \"misread\": PRINTED is a correct word and PUBLISHED substituted a different, wrong "
    "word (an OCR/transcription error in the edition). ACTION restore.\n"
    "- \"source_typo_fixed\": PRINTED is itself a misprint in the 1913 setting and PUBLISHED "
    "shows the correct form, so the edition is BETTER than the page (e.g. PRINTED "
    "'Meternich' vs PUBLISHED 'Metternich'; an obvious typo of a known name/word). ACTION keep.\n"
    "- \"uncertain\": cannot decide from this evidence. ACTION review.\n\n"
    "Period and archaic spelling is CORRECT for 1913 and is NOT a typo — prefer "
    "'modernization' over 'source_typo_fixed' whenever PRINTED is a plausible period form. "
    "Reserve 'source_typo_fixed' for genuine misprints the edition rightly corrected.\n"
    "Reply with ONLY a JSON array: "
    '[{"id":int,"category":"modernization"|"misread"|"source_typo_fixed"|"uncertain",'
    '"action":"restore"|"keep"|"review","reason":"<concise>"}]'
)


def judge_batch(items):
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=180)
    payload = [{"id": it["id"], "PRINTED": it["printed"], "PUBLISHED": it["published"],
                "sentence": it["sentence"],
                "dict_printed": it["votes_printed"], "dict_published": it["votes_published"]}
               for it in items]
    last = None
    for _ in range(3):
        msg = client.messages.create(
            model=MODEL, max_tokens=4000, system=SYSTEM,
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}])
        text = "".join(b.text for b in msg.content if b.type == "text")
        m = re.search(r"\[.*\]", text, re.S)
        if m:
            try:
                return {r["id"]: r for r in json.loads(m.group(0))}
            except json.JSONDecodeError as e:
                last = e
    raise last or ValueError("no JSON array in response")


def _word(s):
    t = re.findall(r"[A-Za-zÀ-ÿ'’]+", s or "")
    return t[0] if t else ""


@functools.lru_cache(maxsize=4096)
def votes(word):
    """How many of the three period dictionaries recognise the word (0-3) — the same
    oracle diff_cleanup uses (defined inline there, replicated here)."""
    if not word:
        return 0
    import adjudicate
    import edgren
    import hoare
    n = 0
    for fn in (lambda w: adjudicate.zingarelli_lookup(w),
               lambda w: edgren.edgren_lookup(w, context_lines=0),
               lambda w: hoare.hoare_lookup(w)):
        try:
            if fn(word):
                n += 1
        except Exception:
            pass
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    load_dotenv(ROOT / ".env")

    data = json.loads(SCANNED.read_text(encoding="utf-8"))
    confirmed = [i for i in data["items"] if i["scan_printed"] in ("source", "other")]

    records = []           # structurally-tagged, no model needed
    to_judge = []          # substitutions for the text judge
    for i, it in enumerate(confirmed):
        printed = (it.get("scan_text") or it.get("source") or "").strip()
        published = (it.get("final") or "").strip()
        # one unique id per confirmed item, shared by structural and judged paths
        # (a previous split assigned two id schemes that collided downstream).
        base = {**it, "id": i, "printed": printed, "published": published}
        if not published and printed:
            records.append({**base, "category": "omission", "action": "restore",
                            "reason": "page carries a word the edition dropped"})
        elif not printed and published:
            records.append({**base, "category": "dittography", "action": "review",
                            "reason": "edition repeats a word the page does not — may be intentional"})
        else:
            base["votes_printed"] = votes(_word(printed))
            base["votes_published"] = votes(_word(published))
            to_judge.append(base)

    if args.limit:
        to_judge = to_judge[:args.limit]
    batches = [to_judge[i:i + BATCH] for i in range(0, len(to_judge), BATCH)]
    print(f"structural: {len(records)}  to judge: {len(to_judge)} in {len(batches)} batches...")

    verdicts = {}
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(judge_batch, b): bi for bi, b in enumerate(batches)}
        for fut in cf.as_completed(futs):
            try:
                verdicts.update(fut.result())
            except Exception as e:
                print(f"  batch {futs[fut]} failed: {e}")

    for it in to_judge:
        v = verdicts.get(it["id"], {})
        records.append({**it, "category": v.get("category", "uncertain"),
                        "action": v.get("action", "review"), "reason": v.get("reason", "(no verdict)")})

    cat = Counter(r["category"] for r in records)
    act = Counter(r["action"] for r in records)
    report = {
        "_note": "Action-classified blind-read deviations. action: restore=adopt the printed "
                 "page form; keep=edition correctly fixed a source typo, do NOT restore; "
                 "review=human decides (dittography / uncertain).",
        "model": MODEL, "confirmed": len(confirmed),
        "category_counts": dict(cat), "action_counts": dict(act),
        "items": sorted(records, key=lambda r: (str(r["chapter"]), r["page"])),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\ncategories: {dict(cat)}")
    print(f"actions: {dict(act)}")
    print(f"  -> RESTORE (adopt page): {act['restore']}")
    print(f"  -> KEEP (source typo the edition fixed): {act['keep']}")
    print(f"  -> REVIEW (dittography/uncertain): {act['review']}")
    print(f"wrote {OUT}")
    st = [r for r in records if r["category"] == "source_typo_fixed"]
    print(f"\nsample source-typo-fixed (KEEP published, do NOT restore): {len(st)}")
    for r in st[:12]:
        print(f"  p.{r['page']}: printed {r['printed']!r} -> published kept {r['published']!r}  ({r['reason'][:45]})")


if __name__ == "__main__":
    main()
