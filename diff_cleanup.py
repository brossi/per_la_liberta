r"""Surface cleanup-introduced corruptions by diffing the pre-cleanup OCR
consensus against the shipped text, across the whole book.

Established by the residual-error audit: the cleanup stage (esp. the symspell
dictionary correction) overwrote source-faithful 1913 words — the OCR was right
and cleanup broke it. `data/reconciled_chapters.json` (3-way OCR consensus,
pre-cleanup) is therefore a ground-truth witness we already hold for every page.

A raw reconciled-vs-final diff is mostly LEGITIMATE cleanup (noise removal,
dehyphenation, garble->word fixes). A *corruption* is the narrow class where
cleanup overwrote a word that was ALREADY a valid period word. We isolate that
class deterministically:

  for each 1:1 word substitution A (pre-cleanup) -> B (final), A != B:
    is A a real period word?  (morphologically reduced: strip enclitic clitics,
    lemmatize, de-archaize j->i)
      tier 1  reduced(A) in the clean it_combined frequency set      -> HIGH
      tier 2  reduced(A) confirmed by >=2 of {Zingarelli, Edgren, Hoare} -> MEDIUM
    if real -> corruption candidate (cleanup changed a valid word)

SCOPE (honest): this catches "valid word overwritten", the dominant, cleanest,
high-precision class. It does NOT catch "OCR garble wrongly fixed to a real but
wrong word" (e.g. reconciled `qnel`/`rav\ivarono` -> wrong `nel`/`ravviarono`):
A there is garble, so the diff gives no signal — that class stays with the
scan-sampling estimate. Elisions/omissions (n:m, e.g. `nell'`->`nelle`) and
accent-only changes are reported separately (accent diffs in OCR are unreliable).

    uv run python diff_cleanup.py            # tier 1 + tier 2 (3 dictionaries)
    uv run python diff_cleanup.py --tier1    # fast clean-dictionary pass only

Output: data/cleanup_corruption_candidates.json (worklist) + a printed summary.
"""

import argparse
import difflib
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).parent
RECON = ROOT / "data" / "reconciled_chapters.json"
FINAL = ROOT / "output" / "italian_clean.md"
DICT = ROOT / "data" / "dictionaries" / "it_combined.txt"
OUT = ROOT / "data" / "cleanup_corruption_candidates.json"

IDS = ["prefazione"] + [f"p1_ch{i:02d}" for i in range(1, 25)] + [f"p2_ch{i:02d}" for i in range(1, 34)]
TOKEN = re.compile(r"[A-Za-zÀ-ÿ]+(?:['’][A-Za-zÀ-ÿ]+)*")
CLITICS = ["gliene", "glielo", "gliela", "melo", "tene", "sene", "ne", "lo", "la",
           "li", "le", "gli", "ci", "vi", "si", "mi", "ti", "ce", "ve"]

_nlp = None


def _nlp_load():
    global _nlp
    if _nlp is None:
        import spacy
        _nlp = spacy.load("it_core_news_lg", disable=["parser", "ner"])
    return _nlp


def deacc(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def load_dict():
    return {ln.split(" ", 1)[0].strip().lower()
            for ln in DICT.read_text(encoding="utf-8").splitlines() if ln.strip()}


def reduced(w):
    """Surface form -> set of lookup candidates: itself, de-archaized (j->i),
    enclitic-stripped stems (+verb endings), and spaCy lemmas of all of these."""
    cands = {w, w.replace("j", "i").replace("J", "I")}
    for c in CLITICS:
        if w.lower().endswith(c) and len(w) - len(c) >= 3:
            s = w[:-len(c)]
            cands |= {s, s + "e", s + "o", s + "i", s + "a"}
    for base in list(cands):
        for t in _nlp_load()(base):
            cands.add(t.lemma_)
    return {c.lower() for c in cands if len(c) >= 4}


def final_bodies():
    md = FINAL.read_text(encoding="utf-8")
    # split() with the capture group yields [pre, range, body, range, body, ...]
    parts = re.split(r"<!-- pages:([\d\-]+) -->", md)
    bodies, ranges = [], []
    for i in range(1, len(parts), 2):
        ranges.append(parts[i])
        bodies.append(re.split(r"\n#{2,3}\s", parts[i + 1])[0] if i + 1 < len(parts) else "")
    return ranges, bodies


def context(tokens, idx, mark, width=8):
    lo, hi = max(0, idx - width), min(len(tokens), idx + width + 1)
    seg = tokens[lo:idx] + [f"⟦{mark}⟧"] + tokens[idx + 1:hi]
    return " ".join(seg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier1", action="store_true", help="clean-dictionary pass only (skip 3 dicts)")
    args = ap.parse_args()

    D = load_dict()
    rec = {c["id"]: c for c in json.loads(RECON.read_text(encoding="utf-8"))}
    ranges, bodies = final_bodies()
    assert len(bodies) == 58, f"expected 58 final chapters, got {len(bodies)}"

    # --- period-dictionary oracle (tier 2), lazily imported + cached ---
    _dict_cache: dict[str, int] = {}

    def votes(word):
        """How many of {Zingarelli, Edgren, Hoare} confirm any reduced form of `word`."""
        if word in _dict_cache:
            return _dict_cache[word]
        import adjudicate, edgren, hoare
        cands = reduced(word)
        n = 0
        for fn in (lambda w: adjudicate.zingarelli_lookup(w),
                   lambda w: edgren.edgren_lookup(w, context_lines=0),
                   lambda w: hoare.hoare_lookup(w)):
            for c in cands:
                try:
                    if fn(c):
                        n += 1
                        break
                except Exception:
                    pass
        _dict_cache[word] = n
        return n

    def classify(A):
        """Return (is_real, confidence, evidence) for the pre-cleanup form A."""
        if any(c in D for c in reduced(A)):
            return True, "high", "it_combined"
        if args.tier1:
            return False, "", ""
        n = votes(A)
        if n >= 2:
            return True, "medium", f"{n}/3 period dicts"
        if n == 1:
            return False, "low", "1/3 period dicts"  # single (often noisy) hit -> treat as legit fix
        return False, "", ""

    candidates, accent_only = [], []
    op = {"replace": 0, "delete": 0, "insert": 0, "nm_replace": 0}
    one2one = 0
    seen_words = 0

    for cid, rng, body in zip(IDS, ranges, bodies):
        if cid not in rec:
            continue
        a = TOKEN.findall(rec[cid]["text"])
        b = TOKEN.findall(body)
        sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            op[tag] = op.get(tag, 0) + max(i2 - i1, j2 - j1)
            if tag != "replace":
                continue
            if (i2 - i1) != 1 or (j2 - j1) != 1:
                op["nm_replace"] += 1
                continue
            one2one += 1
            A, B = a[i1], b[j1]
            if A == B:
                continue
            if deacc(A.lower()) == deacc(B.lower()):
                accent_only.append({"chapter": cid, "pages": rng, "source": A, "final": B,
                                    "context": context(a, i1, A)})
                continue
            seen_words += 1
            is_real, conf, evid = classify(A)
            if is_real:
                candidates.append({
                    "chapter": cid, "pages": rng,
                    "source": A,           # pre-cleanup, source-faithful reading
                    "final": B,            # shipped (corrupted) reading
                    "confidence": conf, "evidence": evid,
                    "context": context(a, i1, A),
                })

    candidates.sort(key=lambda c: (c["confidence"] != "high", c["chapter"]))
    report = {
        "_note": "Cleanup-introduced corruptions: cleanup overwrote a valid period word. "
                 "source = pre-cleanup OCR consensus (faithful); final = shipped text (corrupted).",
        "method": "tier1" if args.tier1 else "tier1+tier2(zingarelli,edgren,hoare >=2/3)",
        "opcodes_tokens": op,
        "one_to_one_subs": one2one,
        "substantive_subs_examined": seen_words,
        "candidates": len(candidates),
        "by_confidence": {k: sum(1 for c in candidates if c["confidence"] == k) for k in ("high", "medium")},
        "accent_only": len(accent_only),
        "items": candidates,
        "accent_only_items": accent_only,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"opcode tokens: {op}")
    print(f"1:1 subs {one2one} | substantive examined {seen_words} | accent-only {len(accent_only)}")
    print(f"CORRUPTION CANDIDATES: {report['candidates']}  "
          f"(high {report['by_confidence']['high']} / medium {report['by_confidence']['medium']})")
    print(f"wrote {OUT}")
    print("\nsample (first 20):")
    for c in candidates[:20]:
        print(f"  [{c['confidence']:>6}] {c['chapter']:>12} {c['source']!r} -> {c['final']!r}  ({c['evidence']})")


if __name__ == "__main__":
    main()
