"""Sampling estimate of the published edition's residual OCR-divergence rate.

The divergence audit (`audit_divergences.py` + `readjudicate.py`) only ever sees
places where the OCR witnesses DISAGREED with the published text. It is blind to
errors every witness shares. This script measures that blind spot the only honest
way — by sampling.

Method (a two-stage capture–recapture over random pages):

  1. Draw a uniform random sample of book-body pages (seeded, reproducible).
  2. BLIND read: transcribe each sampled LoC page verbatim with Gemini 3.1 Pro at
     native resolution — an independent, stronger reader than the IA-Tesseract /
     Google OCR that produced the published text. It is not pinned to the
     published wording.
  3. ALIGN the blind transcription against the published chapter text (difflib
     over word tokens) and enumerate every substantive divergence.
  4. ADJUDICATE each divergence against BOTH physical copies (LoC page + its
     Harvard window) — verbatim ground truth — classifying it:
       published_error  – the page prints something else; the published text is wrong  (COUNTS)
       published_correct– the page matches the published text (blind/align artifact)   (does not count)
       faithful_typo    – the 1913 page itself misprints it and we faithfully kept it   (not an OCR error)
       cannot_read      – damaged in both copies                                        (uncertain)
  5. ESTIMATE the residual published_error rate per character, with a Wilson 95%
     interval, and extrapolate to the whole book.

What this measures: the rate at which the published text DIVERGES FROM WHAT THE
1913 PAGE ACTUALLY PRINTS. What it does NOT measure: whether the 1913 printing is
itself correct (faithful_typo is reported separately, never folded into the error
count). Stage 2 reads catch shared-Tesseract misreads but not glyphs that are
genuinely ambiguous to any reader; that residue surfaces as cannot_read, kept out
of the point estimate and noted in the interval discussion.

    uv run python sample_estimate.py                 # default 40-page sample
    uv run python sample_estimate.py --pages 60      # tighter interval
    uv run python sample_estimate.py --seed 12345    # different draw
    uv run python sample_estimate.py --refresh        # ignore cached page reads
"""

import argparse
import json
import math
import random
import re
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from pathlib import Path

from dotenv import load_dotenv

import vision_review as vr

ROOT = Path(__file__).parent
MARKDOWN = ROOT / "output" / "italian_clean.md"
PAGES = ROOT / "data" / "chapter_pages.json"
OUT = ROOT / "data" / "sample_estimate.json"
CACHE_DIR = ROOT / "state" / "sample_estimate"

# Book-wide size of the published Italian text (non-space characters), the
# denominator the estimate extrapolates onto. Recomputed at run time from the
# parsed chapters so it can never drift from the file.
SYSTEM_BLIND = (
    "You read VERBATIM what a 1913 Italian book page prints — ground truth, not improved "
    "prose. Transcribe EVERY word of the body text exactly as printed: keep accents, "
    "apostrophes, and archaic spelling (boja, riescite, acettano, d'innanzi are valid 1913 "
    "forms); do not modernise or correct. The face is Bodoni/Didone; read at the highest "
    "detail you can. The body is set in TWO COLUMNS — transcribe the FULL left column top to "
    "bottom, THEN the FULL right column; do not stop after one column. Rejoin words hyphenated "
    "across a line break into a single word. SKIP the running head, the page/folio number, and "
    "any catchword. Output PLAIN TEXT only — no JSON, no commentary."
)

SYSTEM_ADJ = (
    "You read VERBATIM what a 1913 Italian book page prints — ground truth. The face is "
    "Bodoni/Didone (c/e and i/r confuse at low resolution; read at full detail). You are shown "
    "TWO INDEPENDENT COPIES of the same 1913 edition: Copy A (LoC) and Copy B (Harvard/Google), "
    "which do not share damage. For each item read the target in BOTH copies and reconcile: if "
    "they agree that is ground truth at high confidence; if they differ, trust the clearer copy "
    "and say which. If a copy does not show the word (wrong page), ignore that copy."
)


# --- published text -----------------------------------------------------------

def parse_chapters() -> list[dict]:
    """Parse italian_clean.md into chapters: {span:(lo,hi), text}. Each chapter is
    '### Heading\\n\\n<!-- pages:N-M -->\\n\\n<body...>' up to the next heading."""
    txt = MARKDOWN.read_text(encoding="utf-8")
    marks = list(re.finditer(r"<!-- pages:(\d+)-(\d+) -->", txt))
    out = []
    for i, m in enumerate(marks):
        lo, hi = int(m.group(1)), int(m.group(2))
        end = marks[i + 1].start() if i + 1 < len(marks) else len(txt)
        body = txt[m.end():end]
        # Trim the trailing next-chapter heading (and its part divider) that sits
        # just before the following marker.
        body = re.split(r"\n#{1,6} ", body)[0]
        out.append({"span": (lo, hi), "text": body.strip()})
    return out


def body_chars(chapters: list[dict]) -> int:
    return sum(len(re.sub(r"\s", "", c["text"])) for c in chapters)


def chapters_for_page(chapters: list[dict], pg: int) -> str:
    """Published text of every chapter whose page span contains pg (1-2 chapters)."""
    return "\n".join(c["text"] for c in chapters if c["span"][0] <= pg <= c["span"][1])


# --- tokenisation & alignment -------------------------------------------------

_WORD_EDGE = re.compile(r"^[^0-9A-Za-zÀ-ÿ]+|[^0-9A-Za-zÀ-ÿ]+$")


def _norm(w: str) -> str:
    return _WORD_EDGE.sub("", w).lower()


def _deaccent(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def tokens(text: str) -> list[tuple[str, str]]:
    """(normalised, original) for each whitespace-split token that has a word core."""
    out = []
    for raw in text.split():
        n = _norm(raw)
        if n:
            out.append((n, raw))
    return out


_OVERSIZE = 12   # a divergence wider than this many words is an alignment artifact, not an error


def divergences(published: str, scan: str):
    """Align a blind page transcription within the published chapter text and return
    (sampled_chars, [divergence...]).

    The chapter text spans several pages, so a stray common word can match far from the
    real region and balloon the span. To prevent that: anchor on the longest match, take
    only the window of published text the size of the blind read around it, then diff
    inside that window. Only opcodes between the first and last matched word count, so
    page headers and un-sampled chapter text are excluded."""
    pa, pb = tokens(published), tokens(scan)
    a = [t[0] for t in pa]
    b = [t[0] for t in pb]
    if not a or not b:
        return 0, []
    anchor = SequenceMatcher(a=a, b=b, autojunk=False).find_longest_match(0, len(a), 0, len(b))
    if anchor.size == 0:
        return 0, []                      # page text not found in the chapter; skip
    slack = 30
    start = max(0, anchor.a - anchor.b - slack)
    end = min(len(a), start + len(b) + 2 * slack)
    paw, aw = pa[start:end], a[start:end]   # published window ≈ one page around the anchor

    sm = SequenceMatcher(a=aw, b=b, autojunk=False)
    ops = sm.get_opcodes()
    eq = [k for k, op in enumerate(ops) if op[0] == "equal"]
    if not eq:
        return 0, []
    first, last = ops[eq[0]], ops[eq[-1]]
    a_lo, a_hi = first[1], last[2]        # matched span within the window
    sampled = sum(len(paw[i][1]) for i in range(a_lo, a_hi))

    divs = []
    for tag, i1, i2, j1, j2 in ops[eq[0]: eq[-1] + 1]:
        if tag == "equal":
            continue
        pub_words = [paw[i][1] for i in range(i1, i2)]
        scan_words = [pb[j][1] for j in range(j1, j2)]
        pub_n = " ".join(aw[i1:i2])
        scan_n = " ".join(b[j1:j2])
        # Classify: oversize blocks are alignment artifacts (kept out of the count);
        # accent/punctuation-only diffs are accento facoltativo, not OCR errors.
        if max(i2 - i1, j2 - j1) > _OVERSIZE:
            kind = "oversize"
        elif _deaccent(pub_n) == _deaccent(scan_n):
            kind = "accent_only"
        else:
            kind = "substantive"
        ctx_lo, ctx_hi = max(0, i1 - 4), min(len(paw), i2 + 4)
        context = " ".join(paw[i][1] for i in range(ctx_lo, ctx_hi))
        divs.append({
            "tag": tag, "kind": kind,
            "published": " ".join(pub_words), "scan_blind": " ".join(scan_words),
            "context": context,
        })
    return sampled, divs


# --- vision passes ------------------------------------------------------------

def _dehyphen(text: str) -> str:
    return re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)


def blind_read(pg: int) -> str:
    """Verbatim plain-text transcription of both columns. The model intermittently
    stops after one column; retry once and keep the longer read (a chapter-opening
    page is legitimately short, so this only helps, never hurts)."""
    user = "Transcribe the full body prose of this 1913 page verbatim — both columns, plain text."
    best = _dehyphen(vr.read_pages([pg], SYSTEM_BLIND, user, model=vr.PRIMARY, json_out=False))
    if len(best) < 1500:
        again = _dehyphen(vr.read_pages([pg], SYSTEM_BLIND, user, model=vr.PRIMARY, json_out=False))
        if len(again) > len(best):
            best = again
    return best


def adjudicate(pg: int, cands: list[dict]) -> list[dict]:
    """One both-copy read classifying every substantive divergence on a page."""
    images = [(f"Copy A (LoC) scan p.{pg}", vr.page_jpeg(pg))]
    for h in vr.harvard_window([pg]):
        try:
            images.append((f"Copy B (Harvard) scan p.{h}", vr.harvard_jpeg(h)))
        except Exception:
            pass
    lines = [
        "Each item is a place where an independent transcription (SCAN_BLIND) disagrees with our "
        "PUBLISHED text. Locate the target via CONTEXT and read what the page ACTUALLY prints, "
        "then classify the disagreement precisely:",
        "  'match'        = the page prints the PUBLISHED form exactly (false positive, no error).",
        "  'misread'      = the page prints a DIFFERENT, correctly-spelled word and PUBLISHED is "
        "wrong (a genuine OCR error — wrong word, dropped word, or spurious word).",
        "  'variant'      = the page prints an archaic/variant SPELLING of the SAME word and "
        "PUBLISHED modernised it (e.g. faccie→facce, riescito→riuscito) — a minor fidelity drift.",
        "  'source_fixed' = the 1913 PAGE ITSELF misprints the word and PUBLISHED shows the "
        "correct form (the published text is BETTER than the source — NOT an error).",
        "  'source_typo'  = the 1913 page misprints the word and PUBLISHED reproduces the misprint.",
        "  'cannot_read'  = illegible/damaged in both copies.",
        "scan_truth: the verbatim printed form on the page. copy: which copy you trusted (A|B|both).",
        "Return ONLY a JSON array of "
        "{idx, scan_truth, verdict, confidence(high|medium|low), copy, note}.",
        "",
    ]
    for i, c in enumerate(cands):
        lines.append(f"idx={i} PUBLISHED={c['published']!r} SCAN_BLIND={c['scan_blind']!r} "
                     f"CONTEXT={c['context']!r}")
    parsed, _raw = vr.read_json_images(images, SYSTEM_ADJ, "\n".join(lines), model=vr.PRIMARY)
    by_idx = {}
    if isinstance(parsed, list):
        for r in parsed:
            if isinstance(r, dict) and "idx" in r:
                try:
                    by_idx[int(r["idx"])] = r
                except (TypeError, ValueError):
                    pass
    out = []
    for i, c in enumerate(cands):
        r = by_idx.get(i, {})
        out.append({**c,
                    "scan_truth": (r.get("scan_truth") or "").strip(),
                    "verdict": r.get("verdict", "cannot_read"),
                    "confidence": r.get("confidence", "low"),
                    "copy": r.get("copy", ""),
                    "note": r.get("note", "")})
    return out


def process_page(pg: int, chapters: list[dict]) -> dict:
    published = chapters_for_page(chapters, pg)
    scan = blind_read(pg)
    sampled, divs = divergences(published, scan)
    subs = [d for d in divs if d["kind"] == "substantive"]
    adjudicated = adjudicate(pg, subs) if subs else []
    return {
        "page": pg,
        "sampled_chars": sampled,
        "accent_only": sum(1 for d in divs if d["kind"] == "accent_only"),
        "oversize": sum(1 for d in divs if d["kind"] == "oversize"),
        "divergences": adjudicated,
        "blind_text": scan,
    }


# --- statistics ---------------------------------------------------------------

def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    """(point, lo, hi) Wilson score interval for a binomial proportion."""
    if n == 0:
        return 0.0, 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d
    return p, max(0.0, centre - half), min(1.0, centre + half)


# --- main ---------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="sampling estimate of residual OCR-divergence rate")
    ap.add_argument("--pages", type=int, default=40, help="number of body pages to sample")
    ap.add_argument("--seed", type=int, default=20260618, help="RNG seed (reproducible draw)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--refresh", action="store_true", help="ignore cached page reads")
    args = ap.parse_args()
    load_dotenv(ROOT / ".env")

    chapters = parse_chapters()
    total_chars = body_chars(chapters)
    pages_map = json.load(open(PAGES, encoding="utf-8"))
    population = sorted({p for pgs in pages_map.values() for p in pgs})

    rng = random.Random(args.seed)
    n = min(args.pages, len(population))
    sample = sorted(rng.sample(population, n))
    print(f"book body: {total_chars} non-space chars across {len(population)} pages "
          f"(pp.{population[0]}-{population[-1]})")
    print(f"sample: {n} pages (seed {args.seed}): {sample}")

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    todo = [p for p in sample if args.refresh or not (CACHE_DIR / f"page_{p:04d}.json").exists()]
    print(f"to read this run: {len(todo)} pages ({len(sample) - len(todo)} cached)\n")

    def work(pg):
        rec = process_page(pg, chapters)
        json.dump(rec, open(CACHE_DIR / f"page_{pg:04d}.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        return rec

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for fut in as_completed([ex.submit(work, p) for p in todo]):
            rec = fut.result()
            done += 1
            errs = sum(1 for d in rec["divergences"] if d["verdict"] == "misread")
            print(f"  [{done}/{len(todo)}] p.{rec['page']}: {rec['sampled_chars']} chars, "
                  f"{len(rec['divergences'])} divergences, {errs} misreads")

    # Aggregate every sampled page from cache.
    recs = [json.load(open(CACHE_DIR / f"page_{p:04d}.json", encoding="utf-8")) for p in sample]
    sampled_chars = sum(r["sampled_chars"] for r in recs)
    verdicts = Counter(d["verdict"] for r in recs for d in r["divergences"])
    misread = verdicts["misread"]                 # genuine OCR errors (wrong/dropped/spurious word)
    variant = verdicts["variant"]                 # period-spelling normalisations (minor fidelity drift)
    coverage = sampled_chars / total_chars if total_chars else 0

    def band(k):
        p, lo, hi = wilson(k, sampled_chars)
        return {"rate_per_10k": round(p * 1e4, 3), "rate_ci95_per_10k": [round(lo * 1e4, 3), round(hi * 1e4, 3)],
                "book_estimate": round(p * total_chars, 1), "book_ci95": [round(lo * total_chars, 1), round(hi * total_chars, 1)]}

    report = {
        "seed": args.seed,
        "pages_sampled": sample,
        "book_chars": total_chars,
        "sampled_chars": sampled_chars,
        "coverage": round(coverage, 4),
        "verdict_counts": dict(verdicts),
        "misreads": misread,
        "fidelity_variants": variant,
        # Headline = genuine misreads. Upper definition folds in period-spelling drift.
        "estimate_misreads": band(misread),
        "estimate_misreads_plus_variants": band(misread + variant),
    }
    json.dump(report, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    b1, b2 = band(misread), band(misread + variant)
    print(f"\n{'='*64}")
    print(f"sampled {sampled_chars} / {total_chars} chars  ({coverage*100:.1f}% of the book)")
    print(f"divergence verdicts: {dict(verdicts)}")
    print(f"  misreads (genuine OCR errors):      {misread}")
    print(f"  fidelity variants (spelling drift): {variant}")
    print(f"  source typos fixed in published:    {verdicts['source_fixed']}  (not errors)")
    print(f"  source typos kept in published:     {verdicts['source_typo']}")
    print(f"  false positives (match):            {verdicts['match']}    "
          f"cannot_read: {verdicts['cannot_read']}")
    print(f"\nHEADLINE — genuine misreads: {misread} in sample "
          f"→ {b1['rate_per_10k']}/10k chars (95% CI {b1['rate_ci95_per_10k'][0]}–{b1['rate_ci95_per_10k'][1]})")
    print(f"  BOOK-WIDE: ~{b1['book_estimate']:.0f} misreads (95% CI {b1['book_ci95'][0]:.0f}–{b1['book_ci95'][1]:.0f})")
    print(f"UPPER — misreads + spelling variants: {misread+variant} "
          f"→ ~{b2['book_estimate']:.0f} book-wide (95% CI {b2['book_ci95'][0]:.0f}–{b2['book_ci95'][1]:.0f})")
    if misread == 0:
        print(f"(0 misreads observed → rule-of-three upper bound ≈ {3/sampled_chars*total_chars:.0f} book-wide)")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
