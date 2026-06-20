r"""Re-audit the unreliable restore/keep verdicts from classify_deviations.py.

The single Sonnet text-judge produced reversed verdicts: it talked itself in circles
(#228 'diventati' -> kept the nonsensical edition word 'ventidue') and emitted actions
that contradict their own reasoning (#326 action=restore while the reason concludes
"source_typo_fixed"). So `action` is unreliable in both directions.

This re-audits the suspect set — every keep verdict, every reason showing a reversal
marker ('wait', 'actually', ...), and every action/reason contradiction — with a
cross-architecture panel (Claude Opus 4.8 + Gemini 3.1 Pro) and a prompt that forces
the check the original skipped: substitute the PRINTED word into the sentence, decide
which reading fits, and make the action match the reasoning.

Where both models agree, that becomes the corrected suggestion (with original_action
kept for transparency); where they split, it's left for the human. Nothing is applied
to the edition — this only fixes the sheet's suggested action.

    uv run python re_audit.py --dry-run   # report, write nothing
    uv run python re_audit.py             # write re_audit + corrected action back
"""

import argparse
import concurrent.futures as cf
import json
import os
import re
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent
CLASSIFIED = ROOT / "data" / "blind_deviations_classified.json"
CLAUDE_MODEL = "claude-opus-4-8"
GEMINI_MODEL = "gemini-3.1-pro-preview"
BATCH = 6

MARK = re.compile(r"\b(wait|actually|hold on|on second|reconsider|scratch that|correction|"
                  r"hmm|never ?mind|let me|but PRINTED|but PUBLISHED|i mean|re-?read)\b", re.I)
KEEPC = re.compile(r"action[:\s]*keep|source[_ ]?typo|published is correct|"
                   r"edition (?:correctly )?fix|fixed by the edition|keep published", re.I)
RESTC = re.compile(r"action[:\s]*restore|restore (?:the )?printed|adopt (?:the )?printed", re.I)

SYSTEM = (
    "You are RE-AUDITING a prior philological triage that is known to contain REVERSED "
    "verdicts. Each item compares a word PRINTED on a 1913 Italian page (ground truth, read "
    "from a high-confidence scan) with the word in a modern PUBLISHED edition. You get the "
    "sentence as it appears in the edition (so it contains the PUBLISHED word) and how many of "
    "three period dictionaries (Zingarelli 1922, Edgren 1901, Hoare 1915) recognise each form.\n\n"
    "Choose ACTION:\n"
    "- \"restore\": the PRINTED page word is correct — a real word or valid period/dialectal "
    "spelling that fits the sentence — and the edition changed it wrongly (a transcription error "
    "or an over-modernization). Adopt the PRINTED word.\n"
    "- \"keep\": the PRINTED page word is a genuine misprint in the 1913 setting and the edition "
    "correctly fixes it. Keep the PUBLISHED word.\n\n"
    "METHOD — follow exactly:\n"
    "1. Substitute the PRINTED word back into the sentence in place of the PUBLISHED word.\n"
    "2. Judge which version is grammatically and semantically correct in context. The PRINTED "
    "word is what the page actually says — do NOT assume the edition is right.\n"
    "3. If PRINTED reads correctly -> restore. If PRINTED is nonsense/ungrammatical and PUBLISHED "
    "fixes an obvious typo -> keep. Period/archaic/dialectal spelling is correct for 1913 and is "
    "NOT a typo.\n"
    "4. Your final action MUST match this reasoning.\n\n"
    "Reply with ONLY a JSON array: "
    '[{"id":int,"action":"restore"|"keep","confidence":"high"|"medium"|"low","reason":"<=25 words"}]'
)


def _payload(items):
    return [{"id": it["id"],
             "PRINTED_on_page": (it.get("scan_text") or it.get("printed") or "").strip(),
             "PUBLISHED_in_edition": (it.get("published") or "").strip(),
             "sentence_as_published": it.get("sentence", ""),
             "dict_printed": it.get("votes_printed"), "dict_published": it.get("votes_published")}
            for it in items]


def _parse_array(text):
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return {}
    try:
        return {r["id"]: r for r in json.loads(m.group(0))}
    except json.JSONDecodeError:
        return {}


def ask_claude(items):
    import anthropic
    c = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=300)
    last = {}
    for _ in range(3):
        r = c.messages.create(model=CLAUDE_MODEL, max_tokens=3000, system=SYSTEM,
                              messages=[{"role": "user",
                                         "content": json.dumps(_payload(items), ensure_ascii=False)}])
        text = "".join(b.text for b in r.content if b.type == "text")
        last = _parse_array(text)
        if last:
            return last
    return last


def ask_gemini(items):
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    user = json.dumps(_payload(items), ensure_ascii=False)
    for _ in range(3):
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=types.Content(role="user", parts=[types.Part.from_text(text=user)]),
            config=types.GenerateContentConfig(system_instruction=SYSTEM, max_output_tokens=4000,
                                               response_mime_type="application/json"))
        got = _parse_array(resp.text or "")
        if got:
            return got
    return {}


def run_panel(items, fn, workers=6):
    batches = [items[i:i + BATCH] for i in range(0, len(items), BATCH)]
    out = {}
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for fut in cf.as_completed([ex.submit(fn, b) for b in batches]):
            try:
                out.update(fut.result())
            except Exception as e:
                print(f"  batch failed: {e}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    load_dotenv(ROOT / ".env")

    report = json.loads(CLASSIFIED.read_text(encoding="utf-8"))
    active = [it for it in report["items"] if not it.get("resolved")]

    def contra(x):
        r, a = x.get("reason", "") or "", x.get("action")
        if a == "restore" and KEEPC.search(r) and not RESTC.search(r):
            return True
        if a == "keep" and RESTC.search(r) and not KEEPC.search(r):
            return True
        return False

    suspect = [x for x in active if x["action"] == "keep"
               or (x.get("reason") and MARK.search(x["reason"])) or contra(x)]
    print(f"re-auditing {len(suspect)} suspect verdicts with Opus 4.8 + Gemini 3.1 Pro...")

    opus = run_panel(suspect, ask_claude)
    gem = run_panel(suspect, ask_gemini)

    overturn, split, confirmed, missing = [], [], 0, 0
    for it in suspect:
        o, g = opus.get(it["id"]), gem.get(it["id"])
        orig = it["action"]
        rec = {"original_action": orig,
               "opus": o and {"action": o.get("action"), "confidence": o.get("confidence"), "reason": o.get("reason")},
               "gemini": g and {"action": g.get("action"), "confidence": g.get("confidence"), "reason": g.get("reason")}}
        if not o or not g:
            rec["consensus"] = "incomplete"
            missing += 1
        elif o["action"] == g["action"]:
            rec["consensus"] = o["action"]
            it["action"] = o["action"]                    # corrected suggestion
            if o["action"] != orig:
                overturn.append((it["id"], orig, o["action"], it.get("published"), it.get("scan_text")))
            else:
                confirmed += 1
        else:
            rec["consensus"] = "split"
            split.append((it["id"], orig, o["action"], g["action"]))
        it["re_audit"] = rec

    print(f"\n  confirmed (panel agrees with original): {confirmed}")
    print(f"  OVERTURNED (panel agrees, differs from original): {len(overturn)}")
    print(f"  split (models disagree -> human): {len(split)}")
    print(f"  incomplete (a model gave no verdict): {missing}")
    oc = Counter((o, n) for _, o, n, *_ in overturn)
    print(f"  overturn directions: {dict(oc)}")
    print("\n  sample overturns:")
    for i, o, n, pub, scan in overturn[:15]:
        print(f"    #{i}  {o}->{n}  page {scan!r} vs edition {pub!r}")
    if split:
        print("\n  splits (need your eye):")
        for i, o, oa, ga in split[:15]:
            print(f"    #{i}  orig={o}  opus={oa}  gemini={ga}")

    if args.dry_run:
        print("\n--dry-run: classified JSON unchanged")
        return
    CLASSIFIED.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {CLASSIFIED}")


if __name__ == "__main__":
    main()
