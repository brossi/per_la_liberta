"""Neutral machine translation (DeepL) of flagged Italian passages — an
independent, non-LLM reference signal for the triage pass.

Why MT helps: NMT renders sense, not surface, so the DIVERGENCE between our
literary translation and a neutral MT discriminates the two remediation tracks.
Our text odd + MT clear and different → we calqued/mistranslated (retranslate).
Our text odd + MT also odd/abstract → the Italian itself is hard (gloss/leave).
It is a reference, not an oracle — frozen idioms can defeat NMT too (it read
"fare il chilo" as "the kilo") — but the comparison is still a strong tell.

Cache-first: every translation is keyed by (source, target, text) and stored in
state/comprehension/mt_cache.json (gitignored), so a passage is paid for once.
The CLI populates the cache for a chosen scope of the ledger; triage_sheet.py
reads the cache (never calls the API itself), so rendering stays offline and API
usage stays explicit. Each cluster's MT is of its MATCHED paragraph (radius 0) —
the unit of comparison — even though the source panel shows a ±1 window.

    uv run python mt.py --breadth 3 --severity high   # populate the hot tier
    uv run python mt.py                                # everything (deduped)
"""

import argparse
import hashlib
import json
import os

import httpx
from dotenv import load_dotenv

from align import italian_window
from comprehension import OUT_DIR

CACHE = os.path.join(OUT_DIR, "mt_cache.json")
SRC, TGT = "IT", "EN-US"
BATCH = 40  # DeepL accepts up to 50 text params/request; stay under


def _endpoint(key: str) -> str:
    # Free keys end in ":fx" and use the api-free host; Pro keys use api.deepl.com.
    return ("https://api-free.deepl.com/v2"
            if key.endswith(":fx") else "https://api.deepl.com/v2")


def _key(text: str) -> str:
    return hashlib.sha1(f"{SRC}|{TGT}|{text}".encode("utf-8")).hexdigest()


def load_cache() -> dict:
    try:
        return json.load(open(CACHE, encoding="utf-8"))
    except FileNotFoundError:
        return {}


def cached(text: str, cache: dict | None = None) -> str | None:
    """Cached MT for a passage, or None — no API call. Used by the renderer."""
    return (cache if cache is not None else load_cache()).get(_key(text))


def translate(texts: list[str]) -> dict:
    """Translate uncached texts via DeepL, update the cache, return it. Idempotent."""
    cache = load_cache()
    todo = sorted({t for t in texts if t and _key(t) not in cache})
    if not todo:
        return cache
    api_key = os.getenv("DEEPL_API_KEY")
    if not api_key:
        raise SystemExit("DEEPL_API_KEY not set (.env)")
    url = _endpoint(api_key) + "/translate"
    with httpx.Client(timeout=60) as cli:
        for i in range(0, len(todo), BATCH):
            chunk = todo[i:i + BATCH]
            # httpx repeats a key for each item when a dict value is a list, which
            # is how DeepL takes multiple texts in one request.
            r = cli.post(url, headers={"Authorization": f"DeepL-Auth-Key {api_key}"},
                         data={"source_lang": SRC, "target_lang": TGT, "text": chunk})
            r.raise_for_status()
            for t, tr in zip(chunk, r.json()["translations"]):
                cache[_key(t)] = tr["text"]
            print(f"  translated {min(i + BATCH, len(todo))}/{len(todo)}")
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    return cache


def usage() -> dict:
    api_key = os.getenv("DEEPL_API_KEY")
    with httpx.Client(timeout=30) as cli:
        r = cli.get(_endpoint(api_key) + "/usage",
                    headers={"Authorization": f"DeepL-Auth-Key {api_key}"})
        r.raise_for_status()
        return r.json()


def scope_texts(args) -> list[str]:
    """The matched-paragraph Italian for every cluster in the chosen ledger scope."""
    rows = [json.loads(l) for l in open(os.path.join(OUT_DIR, "flags.jsonl"), encoding="utf-8")]
    rows = [r for r in rows if r["breadth"] >= args.breadth and r["score"] >= args.min_score
            and (not args.severity or r["severity"] == args.severity)]
    rows.sort(key=lambda r: r["score"], reverse=True)
    if args.top:
        rows = rows[: args.top]
    texts, seen = [], set()
    for r in rows:
        w = italian_window(r["chapter"], r["idx"], radius=0)
        if w and w["text"] and w["text"] not in seen:
            seen.add(w["text"])
            texts.append(w["text"])
    return texts


def main() -> None:
    ap = argparse.ArgumentParser(description="populate the DeepL MT cache for a ledger scope")
    ap.add_argument("--breadth", type=int, default=1)
    ap.add_argument("--severity", choices=["high", "medium", "low"], default=None)
    ap.add_argument("--min-score", type=float, default=0.0)
    ap.add_argument("--top", type=int, default=0)
    args = ap.parse_args()
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

    texts = scope_texts(args)
    print(f"unique matched-paragraph passages in scope: {len(texts)}")
    translate(texts)
    u = usage()
    print(f"DeepL usage: {u['character_count']:,}/{u['character_limit']:,} chars this period")
    print(f"  cache: {CACHE}")


if __name__ == "__main__":
    main()
