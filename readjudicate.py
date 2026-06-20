"""Re-adjudicate divergence-audit candidates against the 1913 page scans, with
Gemini 3.1 Pro as the PRIMARY reader and a Claude pass as escalation.

The earlier scan adjudication (`audit-adjudicate` workflow) used Claude vision
agents. This is the successor: it routes every re-read through `vision_review`
(Gemini 3.1 Pro primary), and escalates only the reads Gemini is unsure of or
that contradict the prior verdict to a second Claude reader — so the strong
vision model carries the bulk and the cross-model check is spent where it counts.

Per chapter, all its in-scope candidates go to the model in one call (the page
images are sent once, not per word). Output is `data/divergence_audit_verdicts_gemini.json`
— the prior Claude-agent verdicts (`data/divergence_audit_verdicts.json`) are
left intact for comparison. Resumable: each chapter's result is cached under
state/readjudication/ and skipped on re-run.

    uv run python readjudicate.py --chapters p1_ch01            # one chapter
    uv run python readjudicate.py --prior uncertain,other       # the open backlog
    uv run python readjudicate.py --all                         # every candidate
    uv run python readjudicate.py --all --no-escalate           # Gemini only
"""

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv

import vision_review as vr

ROOT = Path(__file__).parent
# audit_divergences.py writes the candidate set here; read it from the same path
# so the audit→re-adjudication handoff needs no manual copy.
CANDIDATES = ROOT / "state" / "audit" / "divergence_candidates.json"
PRIOR = ROOT / "data" / "divergence_audit_verdicts.json"
PAGES = ROOT / "data" / "chapter_pages.json"
OUT = ROOT / "data" / "divergence_audit_verdicts_gemini.json"
CACHE_DIR = ROOT / "state" / "readjudication"

SYSTEM = ("You read VERBATIM what a 1913 Italian book page prints — ground truth, not "
          "improved prose. Copy accents, apostrophes, and archaic spelling exactly as printed. "
          "The face is Bodoni/Didone; do not silently modernise (boja, riescite, acettano, "
          "d'innanzi are valid 1913 forms). Read at the highest detail you can. Each page image "
          "is labelled with its scan page number; the body is set in two columns.")

# Escalation re-reads the SAME site in two independent physical copies (same best
# model, Gemini). They do not share damage, so the clean copy resolves what the
# foxed one cannot — the independent copy, not a second model, is the new signal.
SYSTEM_ESC = (SYSTEM + " You are shown TWO INDEPENDENT COPIES of this same 1913 edition: "
              "Copy A (LoC) and Copy B (Harvard/Google). For each target word, read it in BOTH "
              "and reconcile — if they agree, that is your answer at high confidence; if they "
              "differ, report the clearer copy's reading and say which in the note. If a copy does "
              "not show the word (it is the wrong page), ignore that copy; do not let one copy's "
              "damage lower confidence when the other is clear.")


def load_candidates() -> dict[str, list[dict]]:
    raw = json.load(open(CANDIDATES, encoding="utf-8"))
    by_ch: dict[str, list[dict]] = {}
    for grp in ("detector_a", "detector_d"):
        for c in raw[grp]:
            by_ch.setdefault(c["chapter"], []).append(c)
    return by_ch


def load_prior() -> dict[str, dict]:
    return {v["id"]: v for v in json.load(open(PRIOR, encoding="utf-8"))["verdicts"]}


def user_prompt(cands: list[dict]) -> str:
    lines = [
        "For each flagged word, locate it on the page images via its context, then report "
        "EXACTLY what the page prints for the TARGET word (the word that differs between "
        "PUBLISHED and SUGGESTION).",
        "verdict: 'published' = page matches PUBLISHED (flag is a false positive); "
        "'suggestion' = page matches SUGGESTION (the published text is wrong); "
        "'other' = page prints a third form (give it verbatim in scan_reads); "
        "'uncertain' = you cannot confidently locate or read it.",
        "Set scan_reads to the verbatim printed form in every case. Add a one-line note only "
        "when verdict is 'other' or 'uncertain'. Set page to the scan page number (from the image "
        "label) where you found the word.",
        "Return ONLY a JSON array of objects "
        "{id, scan_reads, verdict, confidence(high|medium|low), page, note}.",
        "",
    ]
    for c in cands:
        lines.append(f"id={c['id']} PUBLISHED={c.get('published','')!r} "
                     f"SUGGESTION={c.get('suggestion','')!r} CONTEXT={c.get('context','')!r}")
    return "\n".join(lines)


def _index(parsed) -> dict[str, dict]:
    if not isinstance(parsed, list):
        return {}
    return {r["id"]: r for r in parsed if isinstance(r, dict) and "id" in r}


def _read_primary(cands: list[dict], pages: list[int]) -> dict[str, dict]:
    """Primary (Gemini) pass over a chapter's LoC pages → {id: record}."""
    parsed, _raw = vr.read_json(pages, SYSTEM, user_prompt(cands), model=vr.PRIMARY)
    return _index(parsed)


def _read_escalate(cands: list[dict], loc_pages: list[int], use_harvard: bool) -> dict[str, dict]:
    """Escalation re-read (Gemini) of the SAME site. When the word's page is known
    (use_harvard), add the Harvard window (Copy B) so the independent copy resolves
    damage; when only the chapter is known, re-read Copy A alone (bounded request)."""
    images = [(f"Copy A (LoC) scan p.{p}", vr.page_jpeg(p)) for p in loc_pages]
    if use_harvard:
        for h in vr.harvard_window(loc_pages):
            try:
                images.append((f"Copy B (Harvard) scan p.{h}", vr.harvard_jpeg(h)))
            except Exception:
                pass  # missing/unrenderable Harvard page: fall back to Copy A alone
    system = SYSTEM_ESC if use_harvard else SYSTEM
    parsed, _raw = vr.read_json_images(images, system, user_prompt(cands), model=vr.PRIMARY)
    return _index(parsed)


def needs_escalation(rec: dict, prior: dict | None) -> bool:
    """Escalate low-confidence/uncertain reads, or reads that contradict the prior verdict."""
    if not rec:
        return True
    if rec.get("confidence") == "low" or rec.get("verdict") == "uncertain":
        return True
    if prior and prior.get("scan_reads") and rec.get("scan_reads"):
        return prior["scan_reads"].strip() != rec["scan_reads"].strip()
    return False


def _located_page(rec: dict) -> int | None:
    pg = rec.get("page")
    if isinstance(pg, int):
        return pg
    if isinstance(pg, str) and pg.isdigit():
        return int(pg)
    return None


def adjudicate_chapter(chapter: str, cands: list[dict], pages: list[int],
                       prior: dict[str, dict], escalate: bool) -> list[dict]:
    primary = _read_primary(cands, pages)
    out = []
    escalate_cands = []
    for c in cands:
        rec = primary.get(c["id"], {})
        if escalate and needs_escalation(rec, prior.get(c["id"])):
            escalate_cands.append(c)
        else:
            out.append(_record(c, chapter, rec, prior.get(c["id"]), reader=vr.PRIMARY, escalated=False))
    # Escalate page-targeted: group by the page the primary located the word on, so a
    # call is 1 LoC + its Harvard window (~3 images). When a word's page is unknown,
    # fall back to a single LoC-only re-read of the chapter (bounded; no Harvard).
    groups: dict[tuple, list[dict]] = {}
    for c in escalate_cands:
        pg = _located_page(primary.get(c["id"], {}))
        groups.setdefault((pg,) if pg else tuple(pages), []).append(c)
    for key, group in groups.items():
        use_harvard = len(key) == 1 and key != tuple(pages)
        loc_pages = list(key)
        second = _read_escalate(group, loc_pages, use_harvard=use_harvard)
        for c in group:
            rec = second.get(c["id"]) or primary.get(c["id"], {})
            out.append(_record(c, chapter, rec, prior.get(c["id"]), reader=vr.PRIMARY,
                               escalated=True, second_copy=use_harvard and c["id"] in second))
    return out


def _record(c: dict, chapter: str, rec: dict, prior: dict | None, reader: str,
            escalated: bool, second_copy: bool = False) -> dict:
    return {
        "chapter": chapter, "id": c["id"],
        "scan_reads": (rec.get("scan_reads") or "").strip(),
        "verdict": rec.get("verdict", "uncertain"),
        "confidence": rec.get("confidence", "low"),
        "note": rec.get("note", ""),
        "reader": reader, "escalated": escalated, "second_copy": second_copy,
        "published": c.get("published", ""), "suggestion": c.get("suggestion", ""),
        "prior_verdict": (prior or {}).get("verdict"),
        "prior_scan_reads": (prior or {}).get("scan_reads"),
    }


def select(by_ch: dict[str, list[dict]], prior: dict[str, dict], args) -> dict[str, list[dict]]:
    chapters = set(args.chapters.split(",")) if args.chapters else None
    ids = set(args.ids.split(",")) if args.ids else None
    priors = set(args.prior.split(",")) if args.prior else None
    sel: dict[str, list[dict]] = {}
    for ch, cands in by_ch.items():
        if chapters and ch not in chapters:
            continue
        keep = []
        for c in cands:
            if ids and c["id"] not in ids:
                continue
            if priors and (prior.get(c["id"], {}).get("verdict") not in priors):
                continue
            keep.append(c)
        if keep:
            sel[ch] = keep
    return sel


def main() -> None:
    ap = argparse.ArgumentParser(description="re-adjudicate divergence candidates (Gemini primary)")
    ap.add_argument("--chapters", default="", help="comma-separated chapter ids (p1_ch01,...)")
    ap.add_argument("--ids", default="", help="comma-separated candidate ids (D0000,A0001,...)")
    ap.add_argument("--prior", default="", help="only candidates whose PRIOR verdict is in this set")
    ap.add_argument("--all", action="store_true", help="every candidate (else a scope flag is required)")
    ap.add_argument("--no-escalate", action="store_true", help="Gemini only; never call the Claude reader")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--refresh", action="store_true", help="ignore cached chapter results")
    args = ap.parse_args()
    load_dotenv(ROOT / ".env")

    if not (args.chapters or args.ids or args.prior or args.all):
        raise SystemExit("scope required: pass --chapters / --ids / --prior / --all")

    by_ch = load_candidates()
    prior = load_prior()
    pages = json.load(open(PAGES, encoding="utf-8"))
    scope = select(by_ch, prior, args)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    todo = {ch: cs for ch, cs in scope.items()
            if args.refresh or not (CACHE_DIR / f"{ch}.json").exists()}
    n_sites = sum(len(cs) for cs in scope.values())
    print(f"scope: {len(scope)} chapters / {n_sites} candidates  |  to read this run: {len(todo)} chapters")

    def work(ch):
        recs = adjudicate_chapter(ch, todo[ch], pages[ch], prior, escalate=not args.no_escalate)
        json.dump(recs, open(CACHE_DIR / f"{ch}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return ch, recs

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for fut in as_completed([ex.submit(work, ch) for ch in todo]):
            ch, recs = fut.result()
            done += 1
            esc = sum(1 for r in recs if r["escalated"])
            flips = sum(1 for r in recs if r["prior_verdict"] and r["verdict"] != r["prior_verdict"])
            print(f"  [{done}/{len(todo)}] {ch}: {len(recs)} reads, {esc} escalated, {flips} verdict change vs prior")

    # Merge all cached chapter results in scope into one ledger.
    merged = []
    for ch in scope:
        f = CACHE_DIR / f"{ch}.json"
        if f.exists():
            merged.extend(json.load(open(f, encoding="utf-8")))
    from collections import Counter
    by_verdict = Counter(r["verdict"] for r in merged)
    json.dump({"totals": dict(by_verdict), "verdicts": merged},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nwrote {len(merged)} re-adjudications → {OUT}")
    print(f"  verdicts: {dict(by_verdict)}")
    print(f"  escalated: {sum(1 for r in merged if r['escalated'])} "
          f"(of which {sum(1 for r in merged if r.get('second_copy'))} used Copy B / Harvard)  "
          f"| changed vs prior: {sum(1 for r in merged if r['prior_verdict'] and r['verdict'] != r['prior_verdict'])}")


if __name__ == "__main__":
    main()
