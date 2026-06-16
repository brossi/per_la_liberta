"""Deterministic audit for pipeline-introduced text errors.

Finds places where the *published* text diverges from what the OCR witnesses
say the 1913 scan contains — i.e. errors introduced by reconciliation or
cleanup, not faithful OCR. Pure function of committed artifacts: same inputs ->
byte-identical manifest every run. It MODIFIES NOTHING; it only emits candidate
sites for scan adjudication.

Two complementary detectors (see module README in the audit report header):

  A. Reconciliation word-vote audit (data/flagged_segments.json):
     the reconciler chose a NON-dictionary word when a *similar* dictionary
     reading was available in another witness. Catches all-differ / tie errors
     like 'nielo' chosen over 'cielo'.

  D. Witness-consensus audit (output/italian_clean.md vs copy2 & copy3):
     copy2 AND copy3 agree on a token but the published text differs. Keys on
     witness agreement, NOT the dictionary, so it is dialect-safe and catches
     structural errors invisible to word-level voting (e.g. the 'Dux' case).

Run:  uv run python audit_divergences.py
Out:  state/audit/divergence_candidates.json  +  state/audit/report.md
"""
from __future__ import annotations

import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from utils import normalize_for_comparison

BASE = Path(__file__).parent
DATA = BASE / "data"
OUT = BASE / "output"
AUDIT = BASE / "state" / "audit"


# ---------------------------------------------------------------- dictionary

def _strip(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn").lower()


def load_dict() -> set[str]:
    words: set[str] = set()
    for ln in (DATA / "dictionaries" / "it_combined.txt").open(encoding="utf-8"):
        parts = ln.split()
        if parts:
            words.add(_strip(parts[0]))
    return words


def in_dict(word: str, words: set[str]) -> bool:
    w = _strip("".join(c for c in (word or "") if c.isalpha() or c == "'"))
    return bool(w) and (w in words or w.replace("'", "") in words)


def edit_distance(a: str, b: str) -> int:
    a, b = _strip(a), _strip(b)
    if not a:
        return len(b)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


# ---------------------------------------------------------------- detector A

def detector_a(words: set[str]) -> list[dict]:
    """Reconciliation chose a non-dict word when a similar dict reading existed."""
    seg = json.loads((DATA / "flagged_segments.json").read_text(encoding="utf-8"))
    out = []
    for i, s in enumerate(seg):
        chosen = s["chosen"]
        alts = [a for a in (s.get("word_copy1"), s.get("word_copy2"), s.get("word_copy3")) if a]
        if in_dict(chosen, words):
            continue
        # dictionary alternatives present among the witness readings
        dict_alts = [a for a in alts if a != chosen and in_dict(a, words)]
        if not dict_alts:
            continue
        # best = closest dict alt to the chosen token (a true OCR fix is a small edit;
        # a wildly different short word is an alignment artifact -> lower confidence)
        best = min(dict_alts, key=lambda a: (edit_distance(chosen, a), abs(len(a) - len(chosen))))
        dist = edit_distance(chosen, best)
        out.append({
            "id": f"A{i:04d}",
            "detector": "A_recon_wordvote",
            "chapter": s["chapter"],
            "paragraph": s.get("paragraph"),
            "published": chosen,
            "witnesses": {"copy1": s.get("word_copy1"), "copy2": s.get("word_copy2"), "copy3": s.get("word_copy3")},
            "scores": {"copy1": s.get("score1"), "copy2": s.get("score2"), "copy3": s.get("score3")},
            "suggestion": best,
            "edit_distance": dist,
            "confidence": "high" if dist <= 2 and abs(len(best) - len(chosen)) <= 2 else "low",
            "resolution_method": s.get("resolution_method"),
            "context": s.get("context", ""),
        })
    return out


# ---------------------------------------------------------------- detector D

WORD_RE = re.compile(r"\S+")


def _tok_norm(t: str) -> str:
    return _strip("".join(c for c in t if c.isalnum() or c == "'"))


def _chapters_from_markdown(md: str) -> list[tuple[str, str]]:
    """Return [(slug_id, text)] for content chapters, mirroring parse_italian_markdown."""
    from translate import parse_italian_markdown
    return [(c["id"], c["text"]) for c in parse_italian_markdown(md) if not c.get("is_structural")]


def _locate_region(needle_norm: str, hay_norm: str) -> tuple[int, int] | None:
    """Approximate [start,end) of needle within hay (both normalized).

    Uses many small fixed-size anchor windows (18 chars, stride 30): short runs
    survive garbled OCR ~90% of the time, where 200-char anchors never match.
    The region start is the median of per-anchor start estimates.
    """
    if len(needle_norm) < 60:
        return None
    win, stride = 18, 30
    starts = []
    for off in range(0, len(needle_norm) - win, stride):
        pos = hay_norm.find(needle_norm[off:off + win])
        if pos >= 0:
            starts.append(pos - off)
    if len(starts) < 5:
        return None
    starts.sort()
    med = starts[len(starts) // 2]
    start = max(0, med)
    end = min(len(hay_norm), med + len(needle_norm))
    return start, end


def _witness_region_tokens(ch_text: str, wit_norm: str, wit_norm_to_orig: list[int], wit_orig: str) -> list[str] | None:
    needle = normalize_for_comparison(ch_text)
    reg = _locate_region(needle, wit_norm)
    if reg is None:
        return None
    ns, ne = reg
    pad = 60
    o_start = wit_norm_to_orig[max(0, ns - pad)] if ns < len(wit_norm_to_orig) else 0
    o_end = wit_norm_to_orig[min(len(wit_norm_to_orig) - 1, ne + pad)]
    return WORD_RE.findall(wit_orig[o_start:o_end])


def _aligned_partner(pub_tok_norms: list[str], wit_tok_norms: list[str]) -> dict[int, int]:
    """Map published-token index -> aligned witness-token index.

    Includes 'equal' blocks (identical) AND 'replace' blocks of matching span
    length (unambiguous 1:1 substitution) — the latter is where divergences live,
    so they must be captured, not discarded.
    """
    sm = SequenceMatcher(a=pub_tok_norms, b=wit_tok_norms, autojunk=False)
    m: dict[int, int] = {}
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("equal", "replace") and (i2 - i1) == (j2 - j1):
            for d in range(i2 - i1):
                m[i1 + d] = j1 + d
    return m


def detector_d(words: set[str]) -> list[dict]:
    """Published text disagrees with a copy2 & copy3 token-level agreement."""
    from reconcile import _build_norm_map  # reuse the pipeline's norm-position mapper

    cleaned_chapters = _chapters_from_markdown((OUT / "italian_clean.md").read_text(encoding="utf-8"))
    # map slug ids -> p1_chNN ids by order (both are sequential, 58 each)
    page_ids = list(json.loads((DATA / "chapter_pages.json").read_text(encoding="utf-8")).keys())

    c2 = (DATA / "copy2_raw.txt").read_text(encoding="utf-8")
    c3 = (DATA / "copy3_raw.txt").read_text(encoding="utf-8")
    c2_norm, c2_map = _build_norm_map(c2)
    c3_norm, c3_map = _build_norm_map(c3)

    out = []
    for idx, (slug, text) in enumerate(cleaned_chapters):
        page_id = page_ids[idx] if idx < len(page_ids) else slug
        pub_tokens = WORD_RE.findall(text)
        pub_norm = [_tok_norm(t) for t in pub_tokens]
        w2 = _witness_region_tokens(text, c2_norm, c2_map, c2)
        w3 = _witness_region_tokens(text, c3_norm, c3_map, c3)
        if not w2 or not w3:
            continue
        w2n = [_tok_norm(t) for t in w2]
        w3n = [_tok_norm(t) for t in w3]
        a2 = _aligned_partner(pub_norm, w2n)
        a3 = _aligned_partner(pub_norm, w3n)
        for i, pt in enumerate(pub_norm):
            if not pt or i not in a2 or i not in a3:
                continue
            t2, t3 = w2n[a2[i]], w3n[a3[i]]
            if not t2 or t2 != t3:      # require copy2 & copy3 to agree
                continue
            if pt == t2:                # published already matches consensus
                continue
            pub_orig, cons_orig = pub_tokens[i], w2[a2[i]]
            # Noise-only filters: a real word-level divergence is a small edit on
            # a non-trivial token. The edit<=2 / len>=4 / no-hyphen bounds reject
            # alignment-shift junk (io/ra, nel/n) and line-break fragments. The
            # dictionary is NOT used to filter -- only the scan can say whether the
            # pipeline's override of a 2-witness agreement was right (cleanup fix),
            # a fidelity loss (archaic->modern), or a corruption. Clustering +
            # scan adjudication sort that out downstream.
            if len(t2) < 4 or edit_distance(pt, t2) > 2:
                continue
            if "-" in pub_orig or "-" in cons_orig:
                continue
            out.append({
                "id": f"D{len(out):04d}",
                "detector": "D_witness_consensus",
                "chapter": page_id,
                "slug": slug,
                "published": pub_orig,
                "witnesses": {"copy2": w2[a2[i]], "copy3": w3[a3[i]]},
                "suggestion": cons_orig,
                "transform": f"{pt} <- {t2}",
                "edit_distance": edit_distance(pt, t2),
                "published_in_dict": in_dict(pub_orig, words),
                "consensus_in_dict": in_dict(cons_orig, words),
                "context": " ".join(pub_tokens[max(0, i - 5):i + 6]),
            })
    return out


# ---------------------------------------------------------------- main

def main() -> None:
    from collections import Counter
    AUDIT.mkdir(parents=True, exist_ok=True)
    words = load_dict()
    a = detector_a(words)
    d = detector_d(words)
    # Cluster D by transformation: recurring transforms are systematic pipeline
    # behaviour (mostly archaic->modern normalization) -> one policy decision;
    # singletons are where localized corruptions hide -> individual scan checks.
    tcount = Counter(c["transform"] for c in d)
    for c in d:
        c["cluster_size"] = tcount[c["transform"]]
        c["systematic"] = tcount[c["transform"]] >= 3
    systematic = sorted({c["transform"]: c["cluster_size"] for c in d if c["systematic"]}.items(),
                        key=lambda x: -x[1])
    (AUDIT / "divergence_candidates.json").write_text(
        json.dumps({"detector_a": a, "detector_d": d,
                    "systematic_transforms": systematic}, ensure_ascii=False, indent=2), encoding="utf-8")

    def fa(c):
        return (f"- [{c['id']}] {c['chapter']} p{c['paragraph']}  "
                f"chose **{c['published']!r}** -> **{c['suggestion']!r}** (dist {c['edit_distance']}, {c['confidence']})\n"
                f"      witnesses {c['witnesses']}  | ctx: …{c['context'][:70]}…")

    def fd(c):
        return (f"- [{c['id']}] {c['chapter']}  published **{c['published']!r}** vs consensus **{c['suggestion']!r}** "
                f"(d{c['edit_distance']}, pub_dict={c['published_in_dict']})\n"
                f"      ctx: …{c['context'][:70]}…")

    d_singletons = [c for c in d if not c["systematic"]]
    lines = ["# Divergence audit — candidate sites (deterministic; nothing modified)\n",
             f"Detector A (reconciliation word-vote): {len(a)}  [{sum(c['confidence']=='high' for c in a)} high]",
             f"Detector D (witness-consensus override): {len(d)}  "
             f"[{len(systematic)} systematic transforms / {len(d_singletons)} singleton+rare sites]\n",
             "## Detector D — systematic transforms (recurring; one policy decision each)\n",
             "Mostly archaic->modern normalization the pipeline applied; witnesses (=scan) keep the archaic form.\n"]
    lines += [f"- {n:3d}x  published `{t.split(' <- ')[0]}` <- witnesses `{t.split(' <- ')[1]}`" for t, n in systematic]
    lines += ["\n## Detector D — singleton + rare sites (individual scan adjudication)\n"]
    lines += [fd(c) for c in d_singletons]
    lines += ["\n## Detector A — high confidence\n"]
    lines += [fa(c) for c in a if c["confidence"] == "high"]
    lines += ["\n## Detector A — low confidence (likely alignment artifacts / rare words)\n"]
    lines += [fa(c) for c in a if c["confidence"] == "low"]
    (AUDIT / "report.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"Detector A: {len(a)} ({sum(c['confidence']=='high' for c in a)} high)")
    print(f"Detector D: {len(d)}  ({len(systematic)} systematic transforms / {len(d_singletons)} singleton+rare)")
    print(f"-> {AUDIT/'divergence_candidates.json'}  and  report.md")


if __name__ == "__main__":
    main()
