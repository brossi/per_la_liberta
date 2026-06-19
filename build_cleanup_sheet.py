r"""Build the human audit sheet for the scan-adjudicated cleanup-corruption worklist.

Consumes `data/cleanup_worklist_scanned.json` (diff -> context-judge -> Gemini
scan-adjudication) and emits a self-contained interactive HTML sheet, grouped by
chapter. Each card shows the source vs final readings, the context sentence, the
text-judge's reasoning, and — crucially — what Gemini read on the actual 1913
scan (with the located page image). The scan verdict PRE-SELECTS the suggested
decision (so confirming agreement is one click), but you must still click to
confirm — you remain the arbiter (human-validation principle). Verdicts persist
in the browser and export to JSON.

    uv run python build_cleanup_sheet.py

Output: state/scan_adjudication/audit.html (gitignored).
"""

import html
import json
from pathlib import Path

ROOT = Path(__file__).parent
SCANNED = ROOT / "data" / "cleanup_worklist_scanned.json"
OUT = ROOT / "state" / "scan_adjudication" / "audit.html"
IMG_REL = "../../docs/assets/page_images/page_{:04d}.png"  # state/scan_adjudication/ -> repo root


def page_img(item):
    """Located Copy A page for this candidate, or the chapter's first page."""
    if item.get("scan_copy") == "A" and item.get("scan_pages"):
        return item["scan_pages"][0]
    return int(item["pages"].split("-")[0])


PAGE_TMPL = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cleanup-corruption audit — Per la Libertà!</title>
<style>
:root{--bg:#f4f1ea;--panel:#fffdf8;--ink:#23201b;--muted:#6f685c;--line:#ddd6c8;
  --src:#1f6b3a;--fin:#9a2b2b;--src-bg:#e2efe6;--fin-bg:#f7e4e1;--accent:#5a4632;--sel:#3a6ea5;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
header{position:sticky;top:0;z-index:10;background:var(--panel);border-bottom:1px solid var(--line);
  padding:.7rem 1rem;box-shadow:0 2px 8px rgba(0,0,0,.06)}
header h1{margin:0 0 .35rem;font-size:1.05rem;font-weight:600}
.bar{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center}
.prog{font-variant-numeric:tabular-nums;color:var(--muted)}.prog b{color:var(--ink)}
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
.card{display:grid;grid-template-columns:1.2fr 320px;gap:1rem;border:1px solid var(--line);
  border-radius:8px;padding:.8rem;background:#fff}
@media(max-width:820px){.card{grid-template-columns:1fr}}
.card.done{border-color:var(--src);background:#fbfdfb}
.tags{display:flex;gap:.4rem;align-items:center;margin-bottom:.4rem;flex-wrap:wrap}
.b{font-size:.68rem;text-transform:uppercase;letter-spacing:.04em;padding:.1rem .45rem;border-radius:4px;font-weight:700}
.b.src{background:var(--src-bg);color:var(--src)}.b.fin{background:var(--fin-bg);color:var(--fin)}
.b.oth{background:#fdf3df;color:#8a6d1c}.b.nf{background:#eee;color:#777}
.b.cap{background:#eef;color:#446}
.ctx{font-family:Georgia,serif;font-size:1.02rem;color:#2c2820;margin:.1rem 0 .55rem}
.ctx b{color:#000}
.pair{display:flex;gap:.5rem;flex-wrap:wrap;align-items:center;font-family:'SF Mono',Menlo,monospace;
  font-size:.92rem;margin-bottom:.4rem}
.lab{font-size:.66rem;color:var(--muted);font-family:-apple-system,sans-serif;text-transform:uppercase;letter-spacing:.04em}
.frag{padding:.12rem .4rem;border-radius:4px}.frag.src{background:var(--src-bg);color:var(--src)}
.frag.fin{background:var(--fin-bg);color:var(--fin)}.arrow{color:var(--muted)}
.scanv{font-size:.85rem;margin:.2rem 0 .5rem;padding:.4rem .55rem;border-radius:6px;background:#f6f3ea;border:1px solid var(--line)}
.scanv .em{font-family:'SF Mono',Menlo,monospace;font-weight:700}
.reason{font-size:.8rem;color:var(--muted);font-style:italic;margin-bottom:.5rem}
.dec{display:flex;gap:.4rem;flex-wrap:wrap;align-items:center}
.dec button{border:1px solid var(--line);background:#fff;border-radius:6px;padding:.28rem .55rem;
  font-size:.8rem;cursor:pointer;color:var(--ink);position:relative}
.dec button.suggested::after{content:"★";position:absolute;top:-7px;right:-5px;font-size:.7rem;color:#caa53a}
.dec button.sel[data-d=restore]{background:var(--src);color:#fff;border-color:var(--src)}
.dec button.sel[data-d=scan]{background:var(--sel);color:#fff;border-color:var(--sel)}
.dec button.sel[data-d=keep]{background:var(--fin);color:#fff;border-color:var(--fin)}
.dec button.sel[data-d=unsure]{background:var(--muted);color:#fff;border-color:var(--muted)}
.notes{margin-top:.5rem;width:100%;font:inherit;font-size:.85rem;padding:.35rem .5rem;
  border:1px solid var(--line);border-radius:5px;resize:vertical;min-height:2rem}
.scanwrap img{width:100%;border:1px solid var(--line);border-radius:6px;background:#fff;cursor:zoom-in;display:block}
.scanwrap a{font-size:.78rem;color:var(--sel);text-decoration:none}
.scanwrap .cap{font-size:.74rem;color:var(--muted);margin-top:.3rem}
dialog.zoom{border:none;padding:0;max-width:96vw;max-height:96vh;background:transparent}
dialog.zoom img{max-width:96vw;max-height:96vh}dialog.zoom::backdrop{background:rgba(0,0,0,.85)}
</style></head><body>
<header>
  <h1>Cleanup-corruption audit &mdash; <i>Per la Libertà!</i> &nbsp;
    <span class="prog"><b id="ndone">0</b>/<span id="ntot">0</span> confirmed</span></h1>
  <div class="bar">
    <span class="chip on" data-f="all">All</span>
    <span class="chip" data-f="unconfirmed">Unconfirmed</span>
    <span class="chip" data-f="source">Scan: source (corruption)</span>
    <span class="chip" data-f="final">Scan: final (false alarm)</span>
    <span class="chip" data-f="other">Scan: other</span>
    <span class="chip" data-f="not_found">Not located</span>
    <button class="act" id="export">Export verdicts JSON</button>
  </div>
</header>
<main id="main"></main>
<dialog class="zoom" id="zoom"><img id="zoomimg" alt=""></dialog>
<script>
const DATA = __DATA__;
const KEY = "pll_cleanup_audit_v1";
let store = JSON.parse(localStorage.getItem(KEY) || "{}");
let filter = "all";
function esc(s){return (s||"").replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));}
function ctxHTML(it){
  let c = esc(it.sentence||"");
  return c.replace("___", `<b>[${esc(it.source)} | ${esc(it.final)}]</b>`);
}
function suggested(it){
  return {source:"restore", other:"scan", final:"keep", not_found:""}[it.scan_printed] || "";
}
function matches(it){
  const v=store[it.key]||{};
  if(filter==="all") return true;
  if(filter==="unconfirmed") return !v.decision;
  return it.scan_printed===filter;
}
function card(it){
  const v=store[it.key]||{}, sug=suggested(it);
  const sv = it.scan_printed;
  const scanbadge = {source:'<span class="b src">scan: source</span>',
    final:'<span class="b fin">scan: final</span>',
    other:'<span class="b oth">scan: other</span>',
    not_found:'<span class="b nf">not located</span>'}[sv]||'';
  const copy = it.scan_copy?`<span class="b cap">Copy ${esc(it.scan_copy)} · ${esc(it.scan_confidence)}</span>`:'';
  const scanline = sv==="not_found"
    ? `Gemini could not locate this on the scan — check manually.`
    : `Scan reads: <span class="em">${esc(it.scan_text||"?")}</span> — ${
        sv==="source"?"matches the pre-cleanup reading (corruption confirmed)":
        sv==="final"?"matches the cleaned reading (cleanup was right)":
        "matches neither candidate"}`;
  const sel=d=>v.decision===d?"sel":"";
  const sug2=d=>d===sug?"suggested":"";
  const scanBtn = (sv==="other" && it.scan_text)
    ? `<button data-d="scan" class="${sel('scan')} ${sug2('scan')}">= Use «${esc(it.scan_text)}»</button>` : "";
  const img=it.img;
  return `<div class="card ${v.decision?'done':''}" data-key="${esc(it.key)}">
    <div>
      <div class="tags">${scanbadge}${copy}
        <span class="b" style="background:#eee;color:#555">${esc(it.signature||'—')}</span></div>
      <div class="ctx">${ctxHTML(it)}</div>
      <div class="pair">
        <span class="lab">pre-cleanup</span><span class="frag src">${esc(it.source)}</span>
        <span class="arrow">→</span>
        <span class="lab">shipped</span><span class="frag fin">${esc(it.final)}</span>
      </div>
      <div class="scanv">${scanline}</div>
      <div class="reason">judge: ${esc(it.reason||"")}</div>
      <div class="dec">
        <button data-d="restore" class="${sel('restore')} ${sug2('restore')}">✓ Restore «${esc(it.source)}»</button>
        ${scanBtn}
        <button data-d="keep" class="${sel('keep')} ${sug2('keep')}">✗ Keep «${esc(it.final)}»</button>
        <button data-d="unsure" class="${sel('unsure')} ${sug2('unsure')}">? Unsure</button>
      </div>
      <textarea class="notes" placeholder="note (optional)…" data-note>${esc(v.note||'')}</textarea>
    </div>
    <div class="scanwrap">
      <img src="${img}" loading="lazy" alt="scan p.${it.imgpage}" data-zoom="${img}">
      <a href="${img}" target="_blank">open full scan ↗</a>
      <div class="cap">LoC p.${it.imgpage}${it.scan_copy==='B'?' · (confirmed via Copy B)':''} — find: <b>${esc(it.source)}</b> / <b>${esc(it.final)}</b></div>
    </div>
  </div>`;
}
function render(){
  const main=document.getElementById("main");
  const groups={};
  for(const it of DATA){(groups[it.chapter]=groups[it.chapter]||[]).push(it);}
  let total=0,done=0,html="";
  for(const ch of Object.keys(groups)){
    const its=groups[ch].filter(matches);
    total+=groups[ch].length;
    const cdone=groups[ch].filter(it=>(store[it.key]||{}).decision).length;
    done+=cdone;
    if(!its.length) continue;
    html+=`<details class="ch" open><summary><span class="id">${ch}</span>
      <span class="meta">${groups[ch].length} candidate(s) · pp.${groups[ch][0].pages}</span>
      <span class="done">${cdone}/${groups[ch].length} confirmed</span></summary>
      <div class="cards">${its.map(card).join("")}</div></details>`;
  }
  main.innerHTML=html||"<p style='color:#6f685c'>Nothing matches this filter.</p>";
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
    chapter:it.chapter,source:it.source,final:it.final,
    scan_printed:it.scan_printed,scan_text:it.scan_text,
    decision:v.decision||null,note:v.note||null};});
  const blob=new Blob([JSON.stringify({generated_from:"cleanup_worklist_scanned",findings:out},null,2)],{type:"application/json"});
  const a=document.createElement("a");a.href=URL.createObjectURL(blob);
  a.download="cleanup_audit_results.json";a.click();
});
render();
</script>
</body></html>
"""


def main():
    data = json.loads(SCANNED.read_text(encoding="utf-8"))["items"]
    items = []
    for i, it in enumerate(data):
        pg = page_img(it)
        items.append({**it,
                      "key": f"{it['chapter']}:{it['source']}:{it['final']}:{i}",
                      "img": IMG_REL.format(pg), "imgpage": pg})
    # order: within chapter, corruptions first
    order = {"source": 0, "other": 1, "not_found": 2, "final": 3}
    items.sort(key=lambda it: (it["chapter"], order.get(it["scan_printed"], 9)))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(PAGE_TMPL.replace("__DATA__", json.dumps(items, ensure_ascii=False)),
                   encoding="utf-8")
    print(f"{len(items)} candidates -> {OUT}")


if __name__ == "__main__":
    main()
