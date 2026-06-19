r"""Generate boxed-word crops for the deviation review sheet.

For each classified deviation, locate the disputed word on its 1913 page and emit a
band crop (full column width, a few lines tall) with a rectangle drawn around the
word — so the human review sheet shows exactly what is printed, in context, no
hunting. Column-splitting removes the cross-gutter bbox ambiguity; the item's true
`page` (NOT scan_pages[0], the first page of the located batch) is the page to read.

bbox uses thinking_level=low — grounding does not need reasoning budget, and default
thinking would cost ~20x across the whole worklist. Crops cache per item (resumable);
items whose word cannot be boxed are recorded with box=null so the sheet falls back
to the full page.

    uv run python box_crops.py --limit 6     # smoke test
    uv run python box_crops.py --workers 8   # full classified worklist

Output: state/deviation_crops/*.png + state/deviation_crops/manifest.json
"""

import argparse
import concurrent.futures as cf
import io
import json
import re
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from PIL import Image, ImageDraw

import vision_review as vr

ROOT = Path(__file__).parent
CLASSIFIED = ROOT / "data" / "blind_deviations_classified.json"
PAGE_DIR = ROOT / "docs" / "assets" / "page_images"
OUT = ROOT / "state" / "deviation_crops"

SYS = "You read a single column of a scanned 1913 Italian book page and return one word's bounding box."


def _word(s):
    t = re.findall(r"[A-Za-zÀ-ÿ'’]+", s or "")
    return t[0] if t else (s or "").strip()


def gutter_x(img):
    g = np.asarray(img.convert("L"))
    dark = (g < 128).sum(axis=0)
    W = img.width
    lo, hi = int(0.40 * W), int(0.60 * W)
    return lo + int(np.argmin(dark[lo:hi]))


def _bbox_in(col, target, ctx, jpeg):
    user = (f'Find the word "{target}" (context: "{ctx[:160]}"). If present return ONLY '
            '{"found":true,"box_2d":[ymin,xmin,ymax,xmax]} normalized 0-1000 to THIS image; '
            'else {"found":false}.')
    # grounding uses no thinking at any level, so low is free; retry to ride out the
    # transient parse/rate failures that otherwise read as false "no-box".
    for _ in range(3):
        parsed, _raw = vr.read_json_images([("column", jpeg)], SYS, user, thinking="low")
        if isinstance(parsed, dict) and (parsed.get("found") or parsed.get("found") is False):
            return parsed
    return {}


def box_item(it):
    pg = it["page"]
    path = PAGE_DIR / f"page_{pg:04d}.png"
    if not path.exists():
        return {"box": None, "reason": "no page image"}
    img = Image.open(path).convert("RGB")
    gx = gutter_x(img)
    target = _word(it["printed"]) or _word(it["published"])
    ctx = it.get("sentence", "")
    cols = [("L", 0, img.crop((0, 0, gx, img.height))),
            ("R", gx, img.crop((gx, 0, img.width, img.height)))]
    for side, xoff, col in cols:
        r = _bbox_in(col, target, ctx, vr._jpeg(col))
        if r.get("found") and r.get("box_2d") and len(r["box_2d"]) == 4:
            W, H = col.width, col.height
            ymin, xmin, ymax, xmax = [c / 1000 for c in r["box_2d"]]
            bx0, by0, bx1, by1 = xmin * W, ymin * H, xmax * W, ymax * H
            bh = max(by1 - by0, 20)
            # band: full column width, ~1.4 lines above and below the word
            cy0, cy1 = max(0, int(by0 - 1.4 * bh)), min(H, int(by1 + 1.4 * bh))
            band = col.crop((0, cy0, W, cy1)).convert("RGB")
            d = ImageDraw.Draw(band)
            pad = max(3, int(0.12 * bh))
            d.rectangle([max(0, bx0 - pad), max(0, by0 - cy0 - pad),
                         min(W, bx1 + pad), min(band.height, by1 - cy0 + pad)],
                        outline=(200, 30, 30), width=4)
            fn = OUT / f"d{it['id']:04d}_p{pg}.png"
            band.save(fn)
            return {"box": [round(x, 1) for x in (xmin, ymin, xmax, ymax)],
                    "column": side, "crop": fn.name, "cropsize": [band.width, band.height]}
    return {"box": None, "reason": "no bbox in either column"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    load_dotenv(ROOT / ".env")
    OUT.mkdir(parents=True, exist_ok=True)

    items = json.loads(CLASSIFIED.read_text(encoding="utf-8"))["items"]
    # box A-copy items only (Copy B uses a different page numbering); priority: restore, review, keep
    order = {"restore": 0, "review": 1, "keep": 2}
    items = [it for it in items if it.get("scan_copy", "A") == "A"]
    items.sort(key=lambda it: order.get(it["action"], 3))
    if args.limit:
        items = items[:args.limit]

    manifest_path = OUT / "manifest.json"
    cache = {}
    if manifest_path.exists() and not args.refresh:
        cache = {m["id"]: m for m in json.loads(manifest_path.read_text(encoding="utf-8"))}

    todo = [it for it in items if it["id"] not in cache or cache[it["id"]].get("box") is None]
    print(f"boxing {len(todo)} items ({len(items) - len(todo)} cached)...")

    def work(it):
        res = box_item(it)
        return {"id": it["id"], "page": it["page"], "action": it["action"],
                "category": it["category"], "published": it["published"],
                "printed": it["printed"], **res}

    done = hit = 0
    results = dict(cache)
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        for fut in cf.as_completed([ex.submit(work, it) for it in todo]):
            m = fut.result()
            results[m["id"]] = m
            done += 1
            hit += 1 if m.get("box") else 0
            if done % 25 == 0 or args.limit:
                print(f"  [{done}/{len(todo)}] d{m['id']:04d} p.{m['page']} "
                      f"{'BOX' if m.get('box') else 'no-box'} {m['printed']!r}")

    manifest = sorted(results.values(), key=lambda m: m["id"])
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    boxed = sum(1 for m in manifest if m.get("box"))
    print(f"\nboxed {boxed}/{len(manifest)} ({100*boxed//max(1,len(manifest))}%)  wrote {manifest_path}")


if __name__ == "__main__":
    main()
