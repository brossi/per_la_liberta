r"""Build the human review sheet for the classified blind-read deviations.

Consumes `data/blind_deviations_classified.json` (blind re-read -> scan-adjudication
-> action classification) and the boxed crops from `box_crops.py`, emitting a
self-contained interactive HTML sheet. Each card shows the disputed word BOXED on
the actual 1913 scan (column-split crop), the printed-vs-published readings, the
judge's category and reasoning, and a PRE-SELECTED suggested action — restore the
page form, keep the edition (a source typo it rightly fixed), or review. You remain
the arbiter: the suggestion is starred, but you click to confirm. Verdicts persist
in the browser and export to JSON.

    uv run python build_deviation_sheet.py

Output: state/deviation_crops/sheet.html (gitignored).
"""

import html
import json
from pathlib import Path

ROOT = Path(__file__).parent
CLASSIFIED = ROOT / "data" / "blind_deviations_classified.json"
CROPS = ROOT / "state" / "deviation_crops"
OUT = CROPS / "sheet.html"
PAGE_REL = "../../docs/assets/page_images/page_{:04d}.png"  # state/deviation_crops/ -> repo root

# suggested decision per classified action
SUGGEST = {"restore": "restore", "keep": "keep", "review": "unsure"}

PAGE_TMPL = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Deviation review — Per la Libertà!</title>
<style>
:root{--bg:#f4f1ea;--panel:#fffdf8;--ink:#23201b;--muted:#6f685c;--line:#ddd6c8;
  --restore:#1f6b3a;--keep:#9a2b2b;--review:#8a6d1c;--restore-bg:#e2efe6;--keep-bg:#f7e4e1;
  --review-bg:#fdf3df;--accent:#5a4632;--sel:#3a6ea5;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
header{position:sticky;top:0;z-index:10;background:var(--panel);border-bottom:1px solid var(--line);
  padding:.7rem 1rem;box-shadow:0 2px 8px rgba(0,0,0,.06)}
header h1{margin:0 0 .35rem;font-size:1.05rem;font-weight:600}
.bar{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center}
.prog{font-variant-numeric:tabular-nums;color:var(--muted)}.prog b{color:var(--ink)}
.legend{font-size:.8rem;color:var(--muted);margin:0 0 .45rem}.legend code{font-size:.92em}
.chip{border:1px solid var(--line);background:#fff;border-radius:999px;padding:.18rem .7rem;
  font-size:.82rem;cursor:pointer;color:var(--muted)}
.chip.on{background:var(--accent);color:#fff;border-color:var(--accent)}
button.act{margin-left:auto;border:1px solid var(--accent);background:var(--accent);color:#fff;
  border-radius:6px;padding:.35rem .8rem;font-size:.85rem;cursor:pointer}
main{max-width:1180px;margin:0 auto;padding:1rem}
.ch{background:var(--panel);border:1px solid var(--line);border-radius:10px;margin:0 0 1.4rem;overflow:hidden}
.ch>summary{list-style:none;cursor:pointer;padding:.6rem .9rem;display:flex;gap:.7rem;
  align-items:baseline;background:#efe9dc}
.ch>summary::-webkit-details-marker{display:none}
.ch>summary .id{font-weight:700}.ch>summary .meta{color:var(--muted);font-size:.83rem}
.ch>summary .done{margin-left:auto;font-size:.83rem;color:var(--muted)}
.cards{padding:1rem;display:flex;flex-direction:column;gap:1rem}
.card{display:grid;grid-template-columns:1.1fr 420px;gap:1rem;border:1px solid var(--line);
  border-radius:8px;padding:.8rem;background:#fff}
@media(max-width:900px){.card{grid-template-columns:1fr}}
.card.done{border-color:var(--restore);background:#fbfdfb}
.tags{display:flex;gap:.4rem;align-items:center;margin-bottom:.4rem;flex-wrap:wrap}
.b{font-size:.68rem;text-transform:uppercase;letter-spacing:.04em;padding:.1rem .45rem;border-radius:4px;font-weight:700}
.b.restore{background:var(--restore-bg);color:var(--restore)}
.b.keep{background:var(--keep-bg);color:var(--keep)}
.b.review{background:var(--review-bg);color:var(--review)}
.b.cat{background:#eef;color:#446}.b.cap{background:#eee;color:#777}
.ctx{font-family:Georgia,serif;font-size:1.02rem;color:#2c2820;margin:.1rem 0 .55rem}
.ctx b{color:#000;background:#fdf3df;padding:0 .15rem;border-radius:3px}
.pair{display:flex;gap:.5rem;flex-wrap:wrap;align-items:center;font-family:'SF Mono',Menlo,monospace;
  font-size:.92rem;margin-bottom:.4rem}
.lab{font-size:.66rem;color:var(--muted);font-family:-apple-system,sans-serif;text-transform:uppercase;letter-spacing:.04em}
.frag{padding:.12rem .4rem;border-radius:4px}
.frag.printed{background:var(--restore-bg);color:var(--restore)}
.frag.published{background:var(--keep-bg);color:var(--keep)}.arrow{color:var(--muted)}
.frag.empty{color:var(--muted);font-style:italic;background:#f0ece2}
.reason{font-size:.8rem;color:var(--muted);font-style:italic;margin-bottom:.5rem}
.dec{display:flex;gap:.4rem;flex-wrap:wrap;align-items:center}
.dec button{border:1px solid var(--line);background:#fff;border-radius:6px;padding:.28rem .55rem;
  font-size:.8rem;cursor:pointer;color:var(--ink);position:relative}
.dec button.suggested::after{content:"\2605";position:absolute;top:-7px;right:-5px;font-size:.7rem;color:#caa53a}
.dec button.sel[data-d=restore]{background:var(--restore);color:#fff;border-color:var(--restore)}
.dec button.sel[data-d=keep]{background:var(--keep);color:#fff;border-color:var(--keep)}
.dec button.sel[data-d=unsure]{background:var(--muted);color:#fff;border-color:var(--muted)}
.notes{margin-top:.5rem;width:100%;font:inherit;font-size:.85rem;padding:.35rem .5rem;
  border:1px solid var(--line);border-radius:5px;resize:vertical;min-height:2rem}
.scanwrap img{width:100%;border:1px solid var(--line);border-radius:6px;background:#fff;cursor:zoom-in;display:block}
.scanwrap a{font-size:.78rem;color:var(--sel);text-decoration:none}
.scanwrap .cap{font-size:.74rem;color:var(--muted);margin-top:.3rem}
.nobox{font-size:.74rem;color:var(--keep);margin-top:.3rem}
dialog.zoom{border:none;padding:0;max-width:96vw;max-height:96vh;background:transparent}
dialog.zoom img{max-width:96vw;max-height:96vh}dialog.zoom::backdrop{background:rgba(0,0,0,.85)}
</style></head><body>
<header>
  <h1>Deviation review &mdash; <i>Per la Libertà!</i> &nbsp;
    <span class="prog"><b id="ndone">0</b>/<span id="ntot">0</span> confirmed</span></h1>
  <div class="legend"><b>Original</b> = the 1913 printed page (ground truth) &nbsp;·&nbsp;
    <b>Derived</b> = our transcription (<code>output/italian_clean.md</code>)</div>
  <div class="bar">
    <span class="chip on" data-f="all">All</span>
    <span class="chip" data-f="undecided">Undecided</span>
    <span class="chip" data-f="restore">Restore</span>
    <span class="chip" data-f="keep">Keep (source typo)</span>
    <span class="chip" data-f="review">Review</span>
    <span class="chip" data-f="omission">Omissions</span>
    <span class="chip" data-f="dittography">Dittography</span>
    <span class="chip" data-f="nobox">No box</span>
    <button class="act" id="export">Export verdicts JSON</button>
  </div>
</header>
<main id="main"></main>
<dialog class="zoom" id="zoom"><img id="zoomimg" alt=""></dialog>
<script>
const DATA = __DATA__;
const KEY = "pll_deviation_audit_v1";
const SUGGEST = {restore:"restore", keep:"keep", review:"unsure"};
let store = {};
try { store = JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch(e) { store = {}; }
let filter = "all";
function esc(s){return (s||"").replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));}
function ctxHTML(it){
  let c = esc(it.sentence||"");
  const w = (it.published||"").replace(/[.,;:!?»«"']/g,"");
  if(w){ const re=new RegExp("("+w.replace(/[.*+?^${}()|[\]\\]/g,"\\$&")+")"); c=c.replace(re,"<b>$1</b>"); }
  return c;
}
function matches(it){
  const v=store[it.key]||{};
  if(filter==="all") return true;
  if(filter==="undecided") return !v.decision;
  if(filter==="nobox") return !it.is_crop;
  if(["restore","keep","review"].includes(filter)) return it.action===filter;
  return it.category===filter;
}
function card(it){
  const v=store[it.key]||{}, sug=SUGGEST[it.action]||"unsure";
  const actbadge={restore:'<span class="b restore">restore</span>',
    keep:'<span class="b keep">keep · source typo</span>',
    review:'<span class="b review">review</span>'}[it.action]||'';
  const cat=`<span class="b cat">${esc(it.category)}</span>`;
  const copy=it.scan_copy?`<span class="b cap">Copy ${esc(it.scan_copy)}${it.scan_confidence?' · '+esc(it.scan_confidence):''}</span>`:'';
  const printed = it.printed ? `<span class="frag printed">${esc(it.printed)}</span>`
                             : `<span class="frag empty">(not in Original)</span>`;
  const published = it.published ? `<span class="frag published">${esc(it.published)}</span>`
                                 : `<span class="frag empty">(missing from Derived)</span>`;
  const sel=d=>v.decision===d?"sel":"";
  const sug2=d=>d===sug?"suggested":"";
  const restoreLbl = it.printed ? `✓ Restore «${esc(it.printed)}»`
                                : `✓ Insert «${esc(it.scan_text||it.printed)}»`;
  const keepLbl = it.published ? `✗ Keep «${esc(it.published)}»` : `✗ Keep (omit)`;
  const img = it.img;
  const cap = it.is_crop
    ? `Copy ${esc(it.scan_copy||'A')} p.${it.page} — boxed: <b>${esc(it.printed)}</b>`
    : `<span class="nobox">no box located — full page p.${it.page}; find <b>${esc(it.printed||it.published)}</b></span>`;
  return `<div class="card ${v.decision?'done':''}" data-key="${esc(it.key)}">
    <div>
      <div class="tags">${actbadge}${cat}${copy}</div>
      <div class="ctx">${ctxHTML(it)}</div>
      <div class="pair">
        <span class="lab">Original</span>${printed}
        <span class="arrow">vs</span>
        <span class="lab">Derived</span>${published}
      </div>
      <div class="reason">judge: ${esc(it.reason||"")}</div>
      <div class="dec">
        <button data-d="restore" class="${sel('restore')} ${sug2('restore')}">${restoreLbl}</button>
        <button data-d="keep" class="${sel('keep')} ${sug2('keep')}">${keepLbl}</button>
        <button data-d="unsure" class="${sel('unsure')} ${sug2('unsure')}">? Unsure</button>
      </div>
      <textarea class="notes" placeholder="custom correction / note (optional)…" data-note>${esc(v.note||'')}</textarea>
    </div>
    <div class="scanwrap">
      <img src="${esc(img)}" loading="lazy" alt="scan p.${it.page}" data-zoom="${esc(img)}">
      <a href="${esc(img)}" target="_blank">open ↗</a>
      <div class="cap">${cap}</div>
    </div>
  </div>`;
}
function render(){
  const main=document.getElementById("main");
  const groups={};
  for(const it of DATA){(groups[it.chapter]=groups[it.chapter]||[]).push(it);}
  let total=0,done=0,h="";
  for(const ch of Object.keys(groups)){
    const its=groups[ch].filter(matches);
    total+=groups[ch].length;
    const cdone=groups[ch].filter(it=>(store[it.key]||{}).decision).length;
    done+=cdone;
    if(!its.length) continue;
    h+=`<details class="ch" open><summary><span class="id">${esc(ch)}</span>
      <span class="meta">${groups[ch].length} deviation(s)</span>
      <span class="done">${cdone}/${groups[ch].length} confirmed</span></summary>
      <div class="cards">${its.map(card).join("")}</div></details>`;
  }
  main.innerHTML=h||"<p style='color:#6f685c'>Nothing matches this filter.</p>";
  document.getElementById("ndone").textContent=Object.values(store).filter(v=>v.decision).length;
  document.getElementById("ntot").textContent=total;
}
document.addEventListener("click",e=>{
  const z=e.target.closest("[data-zoom]");
  if(z){document.getElementById("zoomimg").src=z.dataset.zoom;document.getElementById("zoom").showModal();return;}
  const b=e.target.closest(".dec button");
  if(b){const key=b.closest(".card").dataset.key,d=b.dataset.d;
    store[key]=store[key]||{};store[key].decision=(store[key].decision===d)?null:d;
    localStorage.setItem(KEY,JSON.stringify(store));render();return;}
  const chip=e.target.closest(".chip");
  if(chip){filter=chip.dataset.f;
    document.querySelectorAll(".chip").forEach(c=>c.classList.toggle("on",c===chip));render();return;}
});
document.getElementById("zoom").addEventListener("click",e=>{if(e.target.id==="zoom")e.target.close();});
document.addEventListener("input",e=>{
  const card=e.target.closest(".card");if(!card)return;
  const key=card.dataset.key;store[key]=store[key]||{};
  if(e.target.matches("[data-note]"))store[key].note=e.target.value;
  localStorage.setItem(KEY,JSON.stringify(store));
});
document.getElementById("export").addEventListener("click",()=>{
  const out=DATA.map(it=>{const v=store[it.key]||{};return{
    id:it.id,chapter:it.chapter,page:it.page,published:it.published,printed:it.printed,
    scan_text:it.scan_text,category:it.category,suggested_action:it.action,
    decision:v.decision||null,note:v.note||null};});
  const blob=new Blob([JSON.stringify({generated_from:"blind_deviations_classified",findings:out},null,2)],{type:"application/json"});
  const a=document.createElement("a");a.href=URL.createObjectURL(blob);
  a.download="deviation_audit_results.json";a.click();
});
try { render(); }
catch(e){ document.getElementById("main").innerHTML =
  "<pre style='color:#9a2b2b;white-space:pre-wrap'>render error: "+(e&&e.message)+"\n"+(e&&e.stack)+"</pre>"; }
</script>
</body></html>
"""


def main():
    data = json.loads(CLASSIFIED.read_text(encoding="utf-8"))["items"]
    manifest = {}
    mpath = CROPS / "manifest.json"
    if mpath.exists():
        manifest = {m["id"]: m for m in json.loads(mpath.read_text(encoding="utf-8"))}

    items = []
    for it in data:
        m = manifest.get(it["id"], {})
        is_crop = bool(m.get("box") and m.get("crop"))
        img = m["crop"] if is_crop else PAGE_REL.format(it["page"])
        items.append({
            "id": it["id"], "key": f"{it['chapter']}:{it['page']}:{it['id']}",
            "chapter": it["chapter"], "page": it["page"],
            "action": it["action"], "category": it["category"], "reason": it.get("reason", ""),
            "published": it.get("published", ""), "printed": it.get("printed", ""),
            "scan_text": it.get("scan_text", ""), "scan_copy": it.get("scan_copy", ""),
            "scan_confidence": it.get("scan_confidence", ""), "sentence": it.get("sentence", ""),
            "img": img, "is_crop": is_crop,
        })
    # order: within chapter, restore first, then review, then keep
    order = {"restore": 0, "review": 1, "keep": 2}
    items.sort(key=lambda it: (str(it["chapter"]), order.get(it["action"], 3), it["page"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(PAGE_TMPL.replace("__DATA__", json.dumps(items, ensure_ascii=False)),
                   encoding="utf-8")
    boxed = sum(1 for it in items if it["is_crop"])
    print(f"{len(items)} deviations ({boxed} boxed, {len(items)-boxed} full-page fallback) -> {OUT}")


if __name__ == "__main__":
    main()
