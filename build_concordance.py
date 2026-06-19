"""Deterministic LoC <-> Harvard page concordance for the two 1913 scans.

Both copies are the same edition, so the printed folio (page number, bottom-centre)
is the shared key. LoC scan page N shows folio N-6 (constant, re-verified here).
Harvard PDF page M shows folio f(M); M-f(M) is piecewise-constant, stepping by 1
only at an inserted leaf. We read every folio, fit the offsets, and emit a single
verified lookup table — no per-call offset guessing ever again.

Phases:
  folios  read the bottom-strip folio on every LoC page and every Harvard PDF page
  fit     enforce monotonic folios, fit offsets, build data/page_concordance.json
  audit   cross-check by opening words; emit a human audit sheet (HTML)

    uv run python build_concordance.py --phase folios
    uv run python build_concordance.py --phase fit
    uv run python build_concordance.py --phase audit

Harvard image resolution is striped (~36% of body pages, almost all odd, exist
only at ~1290px); each mapped row records harvard_res = full|low so downstream
adjudication knows when Copy B can settle fine glyphs and when it only corroborates.
"""

import argparse
import io
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import fitz
from dotenv import load_dotenv
from PIL import Image

ROOT = Path(__file__).parent
LOC_DIR = ROOT / "docs" / "assets" / "page_images"
HARVARD_PDF = ROOT / "harvard_perlalibertdall00cresgoog.pdf"
OUT = ROOT / "data" / "page_concordance.json"
CACHE = ROOT / "state" / "concordance"
PAGES = ROOT / "data" / "chapter_pages.json"

PRIMARY = "gemini-3.1-pro-preview"
LOC_FOLIO_OFFSET = 6
STRIP_FRAC = 0.12                     # bottom 12% holds the folio
# Body coverage: folios 1..262 -> LoC scan 7..268. Harvard runs a few pages ahead;
# read a generous superset so the fit has every folio it needs.
LOC_RANGE = range(7, 269)
HARVARD_RANGE = range(5, 276)


def _doc():
    return fitz.open(HARVARD_PDF)


def _largest_pixmap(doc, pdf_pg):
    imgs = doc[pdf_pg - 1].get_images(full=True)
    if not imgs:
        return None
    return max((fitz.Pixmap(doc, im[0]) for im in imgs), key=lambda px: px.width * px.height)


def _bottom_strip_jpeg(im: Image.Image) -> bytes:
    w, h = im.size
    crop = im.crop((0, int(h * (1 - STRIP_FRAC)), w, h))
    b = io.BytesIO()
    crop.convert("RGB").save(b, "JPEG", quality=90)
    return b.getvalue()


def loc_strip(scan_pg: int) -> bytes:
    return _bottom_strip_jpeg(Image.open(LOC_DIR / f"page_{scan_pg:04d}.png"))


def harvard_strip_and_res(doc, pdf_pg: int):
    px = _largest_pixmap(doc, pdf_pg)
    if px is None:
        return None, "none"
    im = Image.frombytes("RGB" if px.n >= 3 else "L", (px.width, px.height), px.samples)
    res = "full" if px.width >= 2000 else "low"
    return _bottom_strip_jpeg(im), res


def _ask_folios(batch: list[tuple[str, bytes]], whole: bool) -> dict:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    parts: list = []
    for label, data in batch:
        parts.append(types.Part.from_text(text=f"[{label}]"))
        parts.append(types.Part.from_bytes(data=data, mime_type="image/jpeg"))
    where = ("Each image is a FULL 1913 book page; the printed page number (folio) is centred at the "
             "BOTTOM (check bottom-centre carefully, also top corners)."
             if whole else
             "Each image is the BOTTOM strip of a 1913 book page; the printed page number (folio) is centred there.")
    parts.append(types.Part.from_text(text=(
        where + " For each, report the digits you see, or null if no number is printed (some pages "
        "omit it). Return ONLY a JSON array [{label, folio}] using the exact bracket labels.")))
    r = client.models.generate_content(
        model=PRIMARY, contents=types.Content(role="user", parts=parts),
        config=types.GenerateContentConfig(response_mime_type="application/json", max_output_tokens=2000))
    out = {}
    try:
        for rec in json.loads(r.text):
            lab = str(rec.get("label", "")).strip("[]")
            f = rec.get("folio")
            out[lab] = re.sub(r"\D", "", str(f)) if f not in (None, "", "null") else None
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return out


def _full_jpeg(doc, label: str) -> bytes | None:
    m = re.match(r"(LoC|Harvard) p\.(\d+)", label)
    if not m:
        return None
    pg = int(m.group(2))
    if m.group(1) == "LoC":
        im = Image.open(LOC_DIR / f"page_{pg:04d}.png")
    else:
        px = _largest_pixmap(doc, pg)
        if px is None:
            return None
        im = Image.frombytes("RGB" if px.n >= 3 else "L", (px.width, px.height), px.samples)
    b = io.BytesIO()
    im.convert("RGB").save(b, "JPEG", quality=88)
    return b.getvalue()


def phase_folios(workers: int, refresh: bool) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    doc = _doc()

    # Build work items as (copy, page, label, jpeg, res).
    items = []
    for n in LOC_RANGE:
        items.append(("loc", n, f"LoC p.{n}", loc_strip(n), "full"))
    for m in HARVARD_RANGE:
        jpeg, res = harvard_strip_and_res(doc, m)
        if jpeg is not None:
            items.append(("harvard", m, f"Harvard p.{m}", jpeg, res))

    # Chunk into batches of 10 strips per call.
    batches = [items[i:i + 10] for i in range(0, len(items), 10)]
    cache_f = CACHE / "folios.json"
    have = json.load(open(cache_f)) if (cache_f.exists() and not refresh) else {}

    todo = [b for b in batches if not all(it[2] in have for it in b)]
    print(f"folio reads: {len(items)} strips in {len(batches)} batches ({len(batches)-len(todo)} cached)")

    def strip_work(batch):
        res = _ask_folios([(it[2], it[3]) for it in batch], whole=False)
        return {it[2]: res.get(it[2]) for it in batch}

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for fut in as_completed([ex.submit(strip_work, b) for b in todo]):
            have.update(fut.result())
            done += 1
            if done % 5 == 0 or done == len(todo):
                json.dump(have, open(cache_f, "w"), ensure_ascii=False, indent=1)
                print(f"  {done}/{len(todo)} strip batches")

    # Backfill: a null strip read is usually a low-res page whose tiny strip lost the
    # digits, not a genuinely unnumbered page. Re-read every null as a FULL page (works
    # even at 1026px). A still-null after this is treated as truly unnumbered.
    label_jpeg = {it[2]: it[3] for it in items}
    nulls = [lab for lab in label_jpeg if have.get(lab) is None]
    full = [(lab, _full_jpeg(doc, lab)) for lab in nulls]
    full = [(lab, j) for lab, j in full if j is not None]
    fbatches = [full[i:i + 6] for i in range(0, len(full), 6)]
    print(f"backfill: re-reading {len(full)} null folios as full pages in {len(fbatches)} batches")
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for fut in as_completed([ex.submit(_ask_folios, b, True) for b in fbatches]):
            for lab, f in fut.result().items():
                if f:
                    have[lab] = f
            done += 1
            if done % 5 == 0 or done == len(fbatches):
                json.dump(have, open(cache_f, "w"), ensure_ascii=False, indent=1)
                print(f"  {done}/{len(fbatches)} backfill batches")
    json.dump(have, open(cache_f, "w"), ensure_ascii=False, indent=1)

    # Persist the resolution map alongside.
    resmap = {str(it[1]): it[4] for it in items if it[0] == "harvard"}
    json.dump(resmap, open(CACHE / "harvard_res.json", "w"), indent=1)
    print(f"wrote {cache_f} ({len(have)} folio reads) and harvard_res.json")


def _load_folios():
    f = json.load(open(CACHE / "folios.json"))
    loc, har = {}, {}
    for k, v in f.items():
        m = re.match(r"(LoC|Harvard) p\.(\d+)", k)
        if not m:
            continue
        pg = int(m.group(2))
        fol = int(v) if v and v.isdigit() else None
        (loc if m.group(1) == "LoC" else har)[pg] = fol
    return loc, har


def phase_fit() -> None:
    loc, har = _load_folios()
    resmap = json.load(open(CACHE / "harvard_res.json"))

    # Keep only Harvard reads whose offset is one of the two valid values; everything
    # else (the 9<->19 flip from misread tens digits, the end-matter 33/10) is rejected.
    clean = {fol: pdf for pdf, fol in sorted(har.items())
             if fol and (pdf - fol) in (8, 9)}
    folios_9 = sorted(f for f, p in clean.items() if p - f == 9)
    folios_8 = sorted(f for f, p in clean.items() if p - f == 8)
    max9, min8 = max(folios_9), min(folios_8)
    assert max9 < min8, f"segments overlap ({max9} >= {min8}); offsets not cleanly piecewise"
    boundary = list(range(max9 + 1, min8))   # folios in the gap (e.g. [131])

    def offset(folio):
        if folio <= max9:
            return 9
        if folio >= min8:
            return 8
        return None   # boundary gap

    # Build the concordance for every body folio (1..262 -> LoC pages 7..268).
    rows = {}
    flagged = []
    for loc_pg in range(7, 269):
        folio = loc_pg - 6
        loc_conf = loc.get(loc_pg) == folio
        off = offset(folio)
        if off is None:
            rows[loc_pg] = {"folio": folio, "loc_page": loc_pg, "harvard_page": None,
                            "harvard_res": None, "method": "boundary",
                            "loc_folio_confirmed": loc_conf, "needs_audit": True}
            flagged.append(loc_pg)
            continue
        hpg = folio + off
        direct = clean.get(folio) == hpg
        below = folio < min(folios_9)        # prefazione folios 1-2: extrapolated
        method = "direct" if direct else ("extrapolated" if below else "interpolated")
        res = resmap.get(str(hpg))
        # A 'direct' page has the SAME printed folio confirmed on BOTH copies, which (same
        # edition) proves they're the same page. Only inferred mappings need a human look;
        # harvard_res is recorded separately as a witness-quality flag, not a mapping doubt.
        audit = method != "direct"
        rows[loc_pg] = {"folio": folio, "loc_page": loc_pg, "harvard_page": hpg,
                        "harvard_res": res, "method": method,
                        "loc_folio_confirmed": loc_conf, "needs_audit": audit}
        if audit:
            flagged.append(loc_pg)

    report = {
        "loc_folio_offset": LOC_FOLIO_OFFSET,
        "harvard_segments": [
            {"folios": [int(min(folios_9)), int(max9)], "harvard_offset": 9},
            {"folios": [int(min8), int(max(folios_8))], "harvard_offset": 8},
        ],
        "boundary_folios_skipped": [int(b) for b in boundary],
        "n_pages": len(rows),
        "n_direct": sum(1 for r in rows.values() if r["method"] == "direct"),
        "n_needs_audit": sum(1 for r in rows.values() if r["needs_audit"]),
        "n_harvard_low_res": sum(1 for r in rows.values() if r["harvard_res"] == "low"),
        "verified": False,
        "map": {str(k): v for k, v in rows.items()},
    }
    json.dump(report, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"segments: folios {min(folios_9)}-{max9} -> +9 ;  {min8}-{max(folios_8)} -> +8")
    print(f"boundary (folio skipped in Harvard): {boundary}")
    print(f"{report['n_pages']} pages: {report['n_direct']} direct, "
          f"{report['n_needs_audit']} need audit ({report['n_harvard_low_res']} low-res Copy B)")
    print(f"wrote {OUT} (verified=false; run --phase audit, then human sign-off)")


def _ask_openings(batch: list[tuple[str, bytes]]) -> dict:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    parts: list = []
    for label, data in batch:
        parts.append(types.Part.from_text(text=f"[{label}]"))
        parts.append(types.Part.from_bytes(data=data, mime_type="image/jpeg"))
    parts.append(types.Part.from_text(text=(
        "Each image is a 1913 book page. For each, give the first ~10 words of the running body "
        "text (top of the left column; skip any chapter title/number). Return ONLY a JSON array "
        "[{label, first_words}] using the exact bracket labels.")))
    r = client.models.generate_content(
        model=PRIMARY, contents=types.Content(role="user", parts=parts),
        config=types.GenerateContentConfig(response_mime_type="application/json", max_output_tokens=2500))
    out = {}
    try:
        for rec in json.loads(r.text):
            out[str(rec.get("label", "")).strip("[]")] = (rec.get("first_words") or "").strip()
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return out


def _save_thumb(im: Image.Image, path: Path, width: int = 760) -> None:
    w, h = im.size
    im.convert("RGB").resize((width, int(h * width / w))).save(path, "JPEG", quality=82)


def _norm_words(s: str) -> list[str]:
    return [w for w in re.sub(r"[^0-9a-zà-ÿ ]", " ", s.lower()).split() if len(w) > 1]


def phase_audit(workers: int) -> None:
    import random
    c = json.load(open(OUT, encoding="utf-8"))
    rows = list(c["map"].values())
    nondirect = [v for v in rows if v["method"] != "direct"]
    direct = [v for v in rows if v["method"] == "direct"]
    sample = random.Random(7).sample(direct, 12)
    audit = sorted(nondirect + sample, key=lambda v: v["loc_page"])

    imgdir = CACHE / "audit_img"
    imgdir.mkdir(parents=True, exist_ok=True)
    doc = _doc()
    tasks, plan = [], []   # plan: per row, the labels + harvard candidate pages
    for v in audit:
        lp = v["loc_page"]
        loc_im = Image.open(LOC_DIR / f"page_{lp:04d}.png")
        _save_thumb(loc_im, imgdir / f"loc_{lp:04d}.jpg")
        loc_lab = f"LoC p.{lp}"
        b = io.BytesIO(); loc_im.convert("RGB").save(b, "JPEG", quality=85)
        tasks.append((loc_lab, b.getvalue()))
        hpgs = [v["harvard_page"]] if v["harvard_page"] else [v["folio"] + 9, v["folio"] + 8]
        hlabs = []
        for hp in hpgs:
            px = _largest_pixmap(doc, hp)
            if px is None:
                continue
            him = Image.frombytes("RGB" if px.n >= 3 else "L", (px.width, px.height), px.samples)
            _save_thumb(him, imgdir / f"har_{hp:04d}.jpg")
            hlab = f"Harvard p.{hp}"
            bb = io.BytesIO(); him.convert("RGB").save(bb, "JPEG", quality=85)
            tasks.append((hlab, bb.getvalue()))
            hlabs.append((hp, hlab))
        plan.append({**v, "loc_lab": loc_lab, "hlabs": hlabs})

    # Read opening words for everything (batched, deduped by label). Cache to disk so
    # rebuilding the interactive sheet never re-hits the model; only unread/blank labels
    # are (re-)read, and blanks get one small-batch retry.
    op_cache = CACHE / "openings.json"
    openings: dict = json.load(open(op_cache)) if op_cache.exists() else {}
    by_label = {lab: data for lab, data in tasks}

    def read_missing(labels, size):
        miss = [(lab, by_label[lab]) for lab in labels if lab in by_label]
        bs = [miss[i:i + size] for i in range(0, len(miss), size)]
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for fut in as_completed([ex.submit(_ask_openings, b) for b in bs]):
                for lab, words in fut.result().items():
                    if words:
                        openings[lab] = words

    todo = [lab for lab in by_label if not openings.get(lab)]
    print(f"audit: {len(audit)} page rows, reading openings for {len(todo)} images (cache has {len(openings)})")
    read_missing(todo, 6)
    still = [lab for lab in by_label if not openings.get(lab)]
    if still:
        print(f"  retrying {len(still)} blank openings in small batches")
        read_missing(still, 2)
    json.dump(openings, open(op_cache, "w"), ensure_ascii=False, indent=1)

    # Build the interactive HTML audit sheet. Each row carries the mapped Harvard page;
    # your verdict (correct / wrong + corrected page / unsure / skipped) is saved to
    # localStorage and exported as JSON for ingestion.
    cells = []
    for p in plan:
        loc_words = openings.get(p["loc_lab"], "")
        loc_key = set(_norm_words(loc_words)[:6])
        mapped = p["harvard_page"] or ""
        har_blocks = []
        any_match = False
        for hp, hlab in p["hlabs"]:
            hw = openings.get(hlab, "")
            match = len(loc_key & set(_norm_words(hw)[:8])) >= 2
            any_match = any_match or match
            tag = "✓ words match" if match else "✗ words differ"
            har_blocks.append(
                f"<div class='har {'ok' if match else 'no'}'>"
                f"<div class='cap'>Harvard p.{hp} <span class='res'>[{p['harvard_res'] or '?'}]</span> {tag}</div>"
                f"<a href='audit_img/har_{hp:04d}.jpg' target=_blank><img src='audit_img/har_{hp:04d}.jpg'></a>"
                f"<div class='ow'>{hw or '<i>(opening unread — verify by image)</i>'}</div></div>")
        auto = "AUTO-OK" if any_match else "REVIEW"
        cells.append(
            f"<tr class='{'autook' if any_match else 'review'}' data-loc='{p['loc_page']}' "
            f"data-folio='{p['folio']}' data-mapped='{mapped}'>"
            f"<td class='meta'>LoC p.{p['loc_page']}<br>folio {p['folio']}<br><b>{p['method']}</b>"
            f"<br><span class='auto'>{auto}</span>"
            "<div class='ctl'>"
            "<button class='b ok' data-v='correct'>✓ correct</button>"
            "<button class='b no' data-v='wrong'>✗ wrong</button>"
            "<button class='b un' data-v='unsure'>? unsure</button>"
            "<button class='b sk' data-v='skipped'>∅ skipped leaf</button>"
            f"<label>Harvard p. <input class='hp' value='{mapped}' size=4></label>"
            "<textarea class='note' placeholder='notes'></textarea>"
            "<div class='status'>— undecided —</div></div></td>"
            f"<td><div class='cap'>LoC p.{p['loc_page']} (folio {p['folio']})</div>"
            f"<a href='audit_img/loc_{p['loc_page']:04d}.jpg' target=_blank><img src='audit_img/loc_{p['loc_page']:04d}.jpg'></a>"
            f"<div class='ow'>{loc_words or '<i>(opening unread — verify by image)</i>'}</div></td>"
            f"<td>{''.join(har_blocks)}</td></tr>")

    js = """
<script>
const KEY='concord_audit_v1';
const store=JSON.parse(localStorage.getItem(KEY)||'{}');
function paint(tr){
  const loc=tr.dataset.loc, v=store[loc]||{};
  tr.querySelectorAll('.b').forEach(b=>b.classList.toggle('sel', b.dataset.v===v.verdict));
  const st=tr.querySelector('.status');
  st.textContent = v.verdict ? (v.verdict.toUpperCase()+(v.verdict==='wrong'?' → Harvard p.'+(v.harvard_page||'?'):'')) : '— undecided —';
  st.className='status '+(v.verdict||'');
  tr.classList.toggle('done', !!v.verdict);
}
function save(tr){
  const loc=tr.dataset.loc;
  const cur=store[loc]||{};
  store[loc]={verdict:cur.verdict||null,
    harvard_page:tr.querySelector('.hp').value.trim(),
    note:tr.querySelector('.note').value.trim(),
    folio:tr.dataset.folio, mapped:tr.dataset.mapped};
  localStorage.setItem(KEY,JSON.stringify(store)); paint(tr); counts();
}
function counts(){
  let n={correct:0,wrong:0,unsure:0,skipped:0,undecided:0};
  document.querySelectorAll('tr[data-loc]').forEach(tr=>{
    const v=(store[tr.dataset.loc]||{}).verdict; n[v||'undecided']++;});
  document.getElementById('counts').textContent =
    `correct ${n.correct} · wrong ${n.wrong} · unsure ${n.unsure} · skipped ${n.skipped} · undecided ${n.undecided}`;
}
document.querySelectorAll('tr[data-loc]').forEach(tr=>{
  const v=store[tr.dataset.loc]||{};
  if(v.harvard_page) tr.querySelector('.hp').value=v.harvard_page;
  if(v.note) tr.querySelector('.note').value=v.note;
  tr.querySelectorAll('.b').forEach(b=>b.onclick=()=>{
    (store[tr.dataset.loc]=store[tr.dataset.loc]||{}).verdict=b.dataset.v; save(tr);});
  tr.querySelector('.hp').onchange=()=>save(tr);
  tr.querySelector('.note').onchange=()=>save(tr);
  paint(tr);
});
counts();
document.getElementById('export').onclick=()=>{
  const blob=new Blob([JSON.stringify(store,null,1)],{type:'application/json'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
  a.download='concordance_audit_results.json'; a.click();
};
document.getElementById('reset').onclick=()=>{if(confirm('Clear all verdicts?')){localStorage.removeItem(KEY);location.reload();}};
</script>"""

    html = ("<!doctype html><meta charset=utf-8><title>Concordance audit</title>"
            "<style>body{font:14px/1.5 system-ui;margin:24px;background:#f6f5f2}"
            "h1{font-weight:600}table{border-collapse:collapse;width:100%}"
            "td,th{border:1px solid #ccc;vertical-align:top;padding:8px}"
            "img{width:360px;display:block;border:1px solid #aaa;margin:4px 0}"
            ".meta{width:200px;font-size:13px}.cap{font-weight:600;font-size:12px}"
            ".ow{font-size:12px;color:#333;max-width:360px}.res{color:#888;font-weight:400}"
            "tr.review{background:#fff4e5}tr.autook{background:#eef7ee}tr.done{background:#e6eef7}"
            ".har.no .cap{color:#c0392b}.har.ok .cap{color:#2e7d32}.har{margin-bottom:10px}"
            ".ctl{margin-top:8px;display:flex;flex-direction:column;gap:4px}"
            ".b{cursor:pointer;border:1px solid #999;background:#fff;border-radius:4px;padding:3px}"
            ".b.sel{background:#2a6b8e;color:#fff;border-color:#2a6b8e}"
            ".note{width:100%;height:34px}.status{font-weight:600;font-size:12px}"
            ".status.correct{color:#2e7d32}.status.wrong{color:#c0392b}.status.skipped{color:#5b2a86}"
            "#bar{position:sticky;top:0;background:#f6f5f2;padding:8px 0;z-index:9}"
            "#bar button{padding:6px 12px;margin-right:8px;cursor:pointer}</style>"
            "<h1>LoC ↔ Harvard concordance — human audit</h1>"
            "<div id=bar><button id=export>⬇ Export verdicts (JSON)</button>"
            "<button id=reset>reset</button><span id=counts></span></div>"
            "<p>Segments: folios 3–130 → Harvard +9; 132–262 → +8. Folio 131 skipped in Harvard "
            f"(boundary). {len(nondirect)} inferred mappings + 12 random 'direct' spot-checks. "
            "Per row: <b>✓ correct</b> if the LoC page and its mapped Harvard page are the same printed page; "
            "<b>✗ wrong</b> and type the real Harvard page; <b>∅ skipped leaf</b> if that folio has no Harvard page. "
            "Verdicts autosave to this browser; click <b>Export</b> when done and hand me the file. "
            "Click any image to open it full-size.</p>"
            "<table><tr><th>info + verdict</th><th>LoC (Copy A)</th><th>Harvard (Copy B)</th></tr>"
            + "".join(cells) + "</table>" + js)
    out_html = CACHE / "audit.html"
    out_html.write_text(html, encoding="utf-8")
    n_review = sum(1 for p in plan if not any(
        len(set(_norm_words(openings.get(p["loc_lab"], ""))[:6]) &
            set(_norm_words(openings.get(hl, ""))[:8])) >= 2 for _, hl in p["hlabs"]))
    print(f"auto-OK: {len(plan)-n_review}/{len(plan)}   need-review: {n_review}")
    print(f"wrote interactive audit sheet → {out_html}")


def phase_lock(results_path: Path) -> None:
    """Ingest the human audit verdicts and lock the concordance. The 33-page sample
    validates the OFFSET MODEL, so direct pages inside a confirmed segment inherit the
    verdict; only explicit corrections and unresolved rows are carried per-page."""
    c = json.load(open(OUT, encoding="utf-8"))
    results = json.load(open(results_path, encoding="utf-8"))
    applied, corrected, unresolved = 0, [], []
    for loc, v in results.items():
        row = c["map"].get(loc)
        if not row:
            continue
        applied += 1
        verd = v.get("verdict")
        row["human"] = verd
        row["human_note"] = v.get("note", "")
        if verd == "correct":
            row["needs_audit"] = False
        elif verd == "wrong":
            hp = str(v.get("harvard_page", "")).strip()
            if hp.isdigit():
                row["harvard_page"] = int(hp); row["method"] = "human"; row["needs_audit"] = False
                corrected.append(loc)
            else:
                row["needs_audit"] = True; unresolved.append(loc)
        elif verd == "skipped":
            row["harvard_page"] = None; row["method"] = "skipped_leaf"; row["needs_audit"] = False
        else:  # unsure / missing
            row["needs_audit"] = True; unresolved.append(loc)

    from collections import Counter
    vc = Counter(v.get("verdict") for v in results.values())
    c["audit"] = {"sample_size": len(results), "verdict_counts": dict(vc),
                  "corrected": corrected, "unresolved": unresolved,
                  "note": f"offset segments human-validated on a {len(results)}-page sample "
                          f"({dict(vc)}); direct pages in a confirmed segment inherit."}
    c["verified"] = True
    json.dump(c, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"applied {applied} verdicts: {len(corrected)} corrected, {len(unresolved)} unresolved {unresolved}")
    print(f"locked {OUT} (verified=true)")


def phase_viewer() -> None:
    """Render every Harvard PDF page (downscaled) and build a flip viewer so a human can
    browse the copy page-for-page and read off the actual page for any folio."""
    doc = _doc()
    outdir = CACHE / "harvard_pages"
    outdir.mkdir(parents=True, exist_ok=True)
    folios = {}
    for k, v in json.load(open(CACHE / "folios.json")).items():
        m = re.match(r"Harvard p\.(\d+)", k)
        if m:
            folios[int(m.group(1))] = v
    rev = {}
    if OUT.exists():
        for loc, row in json.load(open(OUT))["map"].items():
            if row.get("harvard_page"):
                rev[row["harvard_page"]] = int(loc)

    n = doc.page_count
    print(f"rendering {n} Harvard pages to {outdir} (downscaled)")
    for m in range(1, n + 1):
        path = outdir / f"h_{m:04d}.jpg"
        if path.exists():
            continue
        px = _largest_pixmap(doc, m)
        if px is None:
            continue
        im = Image.frombytes("RGB" if px.n >= 3 else "L", (px.width, px.height), px.samples)
        w = 1100
        im.convert("RGB").resize((w, int(im.height * w / im.width))).save(path, "JPEG", quality=80)
        if m % 40 == 0:
            print(f"  {m}/{n}")

    meta = {m: {"folio": folios.get(m), "loc": rev.get(m)} for m in range(1, n + 1)}
    html = """<!doctype html><meta charset=utf-8><title>Harvard page viewer</title>
<style>body{margin:0;font:14px system-ui;background:#222;color:#eee}
#bar{position:fixed;top:0;left:0;right:0;background:#111;padding:8px 12px;display:flex;gap:14px;align-items:center;z-index:9}
#bar input{width:70px}#cap{font-weight:600}#wrap{padding:52px 0 0;text-align:center}
img{max-height:92vh;border:1px solid #555;background:#fff}
button{padding:5px 12px;cursor:pointer}.hint{color:#999}</style>
<div id=bar>
 <button onclick="go(cur-1)">◀ prev</button>
 <button onclick="go(cur+1)">next ▶</button>
 PDF page <input id=jump type=number onchange="go(+this.value)">
 <span id=cap></span>
 <span class=hint>← → arrow keys · caption shows the folio I read + the LoC page it maps to</span>
</div>
<div id=wrap><img id=img></div>
<script>
const META=__META__; const N=__N__; let cur=1;
function go(m){ if(m<1)m=1; if(m>N)m=N; cur=m;
 document.getElementById('img').src='harvard_pages/h_'+String(m).padStart(4,'0')+'.jpg';
 const d=META[m]||{}; document.getElementById('jump').value=m;
 document.getElementById('cap').textContent='Harvard PDF p.'+m+'  ·  printed folio (I read): '+(d.folio||'—')+'  ·  ↔ LoC p.'+(d.loc||'—'); }
document.onkeydown=e=>{if(e.key==='ArrowLeft')go(cur-1);if(e.key==='ArrowRight')go(cur+1);};
go(139);
</script>"""
    html = html.replace("__META__", json.dumps(meta)).replace("__N__", str(n))
    out_html = CACHE / "harvard_viewer.html"
    out_html.write_text(html, encoding="utf-8")
    print(f"wrote viewer → {out_html} (opens at PDF p.139, the folio-130/132 boundary)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True, choices=["folios", "fit", "audit", "lock", "viewer"])
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--results", default=str(Path.home() / "Downloads" / "concordance_audit_results.json"))
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    load_dotenv(ROOT / ".env")
    if args.phase == "folios":
        phase_folios(args.workers, args.refresh)
    elif args.phase == "fit":
        phase_fit()
    elif args.phase == "audit":
        phase_audit(args.workers)
    elif args.phase == "lock":
        phase_lock(Path(args.results))
    elif args.phase == "viewer":
        phase_viewer()


if __name__ == "__main__":
    main()
