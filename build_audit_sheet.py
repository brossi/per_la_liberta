"""Build a human audit sheet for the residual-OCR-divergence findings.

The sampling estimate (`sample_estimate.py`) flags, per sampled page, every place
the *published* Italian text diverges from what the 1913 source scan actually
reads (`scan_truth`), and machine-adjudicates each as misread / variant /
source_fixed / match. Resolving the misreads is a HUMAN step (see the
human-validation-step rule): this script does NOT decide anything — it gathers
the misread/variant findings, groups them under their LoC page scan, and emits a
self-contained interactive HTML sheet so a person can confirm or overturn each
proposed correction against their own eyes, then export the verdicts.

Findings come from the per-page cache `state/sample_estimate/page_NNNN.json`,
restricted to the pages actually in this run's sample (the cache can hold stale
pages from earlier seeds). The LoC native-resolution page image is shown once
per page (never downsampled — the Bodoni face needs native res); the Harvard
counterpart page/resolution from the concordance is surfaced as a cross-check
pointer.

    uv run python build_audit_sheet.py            # misreads + variants
    uv run python build_audit_sheet.py --misreads-only

Output: state/sample_estimate/audit.html (gitignored). Verdicts persist in the
browser (localStorage) and export to JSON via the in-page button.
"""

import argparse
import glob
import html
import json
from pathlib import Path

import vision_review as vr

ROOT = Path(__file__).parent
CACHE = ROOT / "state" / "sample_estimate"
SUMMARY = ROOT / "data" / "sample_estimate.json"
OUT = CACHE / "audit.html"

# state/sample_estimate/audit.html -> repo root is two levels up
IMG_REL = "../../docs/assets/page_images/page_{:04d}.png"


def collect(verdicts_wanted):
    sampled = set(json.loads(SUMMARY.read_text())["pages_sampled"])
    by_page = {}
    for f in sorted(glob.glob(str(CACHE / "page_*.json"))):
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        pg = d["page"]
        if pg not in sampled:
            continue  # stale leftover from an earlier seed
        rows = []
        for oidx, dv in enumerate(d.get("divergences", [])):
            if dv.get("verdict") not in verdicts_wanted:
                continue
            rows.append({
                "page": pg,
                "oidx": oidx,
                "tag": dv.get("tag", ""),
                "published": dv.get("published", ""),
                "scan_blind": dv.get("scan_blind", ""),
                "scan_truth": dv.get("scan_truth", ""),
                "verdict": dv.get("verdict", ""),
                "copy": dv.get("copy", ""),
                "confidence": dv.get("confidence", ""),
                "context": dv.get("context", ""),
                "note": dv.get("note", ""),
            })
        if rows:
            by_page[pg] = {
                "page": pg,
                "img": IMG_REL.format(pg),
                "harvard_page": vr.harvard_page(pg),
                "harvard_res": vr.harvard_res(pg),
                "findings": rows,
            }
    return [by_page[p] for p in sorted(by_page)]


PAGE_TMPL = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Misread audit — Per la Libertà!</title>
<style>
:root{
  --bg:#f4f1ea; --panel:#fffdf8; --ink:#23201b; --muted:#6f685c;
  --line:#ddd6c8; --pub:#9a2b2b; --truth:#1f6b3a; --accent:#5a4632;
  --pub-bg:#f7e4e1; --truth-bg:#e2efe6; --sel:#3a6ea5;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:16px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
header{position:sticky;top:0;z-index:10;background:var(--panel);
  border-bottom:1px solid var(--line);padding:.7rem 1rem;
  box-shadow:0 2px 8px rgba(0,0,0,.06)}
header h1{margin:0 0 .35rem;font-size:1.05rem;font-weight:600}
.bar{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center}
.prog{font-variant-numeric:tabular-nums;color:var(--muted)}
.prog b{color:var(--ink)}
.chip{border:1px solid var(--line);background:#fff;border-radius:999px;
  padding:.18rem .7rem;font-size:.82rem;cursor:pointer;color:var(--muted)}
.chip.on{background:var(--accent);color:#fff;border-color:var(--accent)}
button.act{margin-left:auto;border:1px solid var(--accent);background:var(--accent);
  color:#fff;border-radius:6px;padding:.35rem .8rem;font-size:.85rem;cursor:pointer}
main{max-width:1180px;margin:0 auto;padding:1rem}
.page{background:var(--panel);border:1px solid var(--line);border-radius:10px;
  margin:0 0 1.4rem;overflow:hidden}
.page>summary{list-style:none;cursor:pointer;padding:.6rem .9rem;
  display:flex;gap:.7rem;align-items:baseline;background:#efe9dc}
.page>summary::-webkit-details-marker{display:none}
.page>summary .pg{font-weight:700;font-size:1.05rem}
.page>summary .meta{color:var(--muted);font-size:.83rem}
.page>summary .done{margin-left:auto;font-size:.83rem;color:var(--muted)}
.body{display:grid;grid-template-columns:minmax(320px,1fr) 1.1fr;gap:1rem;padding:1rem}
@media(max-width:820px){.body{grid-template-columns:1fr}}
.scanwrap{position:relative}
.scan{position:sticky;top:5.2rem}
.scan img{width:100%;border:1px solid var(--line);border-radius:6px;
  background:#fff;cursor:zoom-in;display:block}
.scan a{font-size:.8rem;color:var(--sel);text-decoration:none}
.harv{font-size:.8rem;color:var(--muted);margin-top:.35rem}
.cards{display:flex;flex-direction:column;gap:.8rem}
.card{border:1px solid var(--line);border-radius:8px;padding:.7rem .8rem;background:#fff}
.card.resolved{border-color:var(--truth);background:#fbfdfb}
.tags{display:flex;gap:.4rem;align-items:center;margin-bottom:.4rem;flex-wrap:wrap}
.v{font-size:.7rem;text-transform:uppercase;letter-spacing:.04em;
  padding:.1rem .45rem;border-radius:4px;font-weight:700}
.v.misread{background:var(--pub-bg);color:var(--pub)}
.v.variant{background:#fdf3df;color:#8a6d1c}
.two{font-size:.7rem;color:var(--truth);font-weight:700}
.one{font-size:.7rem;color:var(--muted)}
.ctx{font-family:Georgia,'Times New Roman',serif;font-size:1.02rem;
  color:#2c2820;margin:.1rem 0 .55rem;line-height:1.45}
.ctx mark{background:var(--pub-bg);color:var(--pub);padding:0 .1em;border-radius:2px}
.pair{display:flex;gap:.6rem;flex-wrap:wrap;align-items:center;
  font-family:'SF Mono',Menlo,Consolas,monospace;font-size:.92rem;margin-bottom:.5rem}
.pair .lab{font-size:.68rem;color:var(--muted);font-family:inherit;
  font-family:-apple-system,sans-serif;text-transform:uppercase;letter-spacing:.04em}
.frag{padding:.12rem .4rem;border-radius:4px}
.frag.pub{background:var(--pub-bg);color:var(--pub)}
.frag.truth{background:var(--truth-bg);color:var(--truth)}
.arrow{color:var(--muted)}
.blind{font-size:.78rem;color:var(--muted);margin-bottom:.5rem}
.blind code{font-family:'SF Mono',Menlo,monospace;background:#f1ede3;padding:0 .25em;border-radius:3px}
.note-m{font-size:.82rem;color:var(--muted);font-style:italic;margin-bottom:.55rem}
.dec{display:flex;gap:.4rem;flex-wrap:wrap;align-items:center}
.dec button{border:1px solid var(--line);background:#fff;border-radius:6px;
  padding:.28rem .6rem;font-size:.82rem;cursor:pointer;color:var(--ink)}
.dec button.sel[data-d=apply]{background:var(--truth);color:#fff;border-color:var(--truth)}
.dec button.sel[data-d=keep]{background:var(--pub);color:#fff;border-color:var(--pub)}
.dec button.sel[data-d=custom]{background:var(--sel);color:#fff;border-color:var(--sel)}
.dec button.sel[data-d=skip]{background:var(--muted);color:#fff;border-color:var(--muted)}
.custom{margin-top:.5rem;display:none;gap:.4rem;flex-wrap:wrap}
.custom.show{display:flex}
.custom input{font-family:'SF Mono',Menlo,monospace;font-size:.9rem;
  padding:.3rem .5rem;border:1px solid var(--line);border-radius:5px;min-width:180px}
.notes{margin-top:.5rem;width:100%;font:inherit;font-size:.85rem;
  padding:.4rem .5rem;border:1px solid var(--line);border-radius:5px;resize:vertical;min-height:2.2rem}
dialog.zoom{border:none;padding:0;max-width:96vw;max-height:96vh;background:transparent}
dialog.zoom img{max-width:96vw;max-height:96vh}
dialog.zoom::backdrop{background:rgba(0,0,0,.85)}
</style></head><body>
<header>
  <h1>Misread audit &mdash; <i>Per la Libertà!</i> &nbsp;<span class="prog"><b id="ndone">0</b>/<span id="ntot">0</span> resolved</span></h1>
  <div class="bar">
    <span class="chip on" data-f="all">All</span>
    <span class="chip" data-f="unresolved">Unresolved</span>
    <span class="chip" data-f="misread">Misreads</span>
    <span class="chip" data-f="variant">Variants</span>
    <span class="chip" data-f="two">Two-copy confirmed</span>
    <button class="act" id="export">Export verdicts JSON</button>
  </div>
</header>
<main id="main"></main>
<dialog class="zoom" id="zoom"><img id="zoomimg" alt=""></dialog>
<script>
const DATA = __DATA__;
const KEY = "pll_misread_audit_v1";
let store = JSON.parse(localStorage.getItem(KEY) || "{}");
let filter = "all";

function fid(f){ return f.page + ":" + f.oidx; }
function save(){ localStorage.setItem(KEY, JSON.stringify(store)); render(); }

function esc(s){ return (s||"").replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c])); }
function ctxHTML(f){
  let c = esc(f.context);
  if(f.published){
    const p = esc(f.published);
    const i = c.indexOf(p);
    if(i>=0) c = c.slice(0,i)+"<mark>"+p+"</mark>"+c.slice(i+p.length);
  }
  return c;
}

function matches(f){
  const v = store[fid(f)] || {};
  if(filter==="all") return true;
  if(filter==="unresolved") return !v.decision;
  if(filter==="misread") return f.verdict==="misread";
  if(filter==="variant") return f.verdict==="variant";
  if(filter==="two") return f.copy==="both";
  return true;
}

function card(f){
  const id = fid(f), v = store[id] || {};
  const two = f.copy==="both"
    ? '<span class="two">✓ both copies</span>'
    : '<span class="one">LoC only</span>';
  const blind = (f.scan_blind && f.scan_blind!==f.scan_truth)
    ? `<div class="blind">blind read: <code>${esc(f.scan_blind)}</code></div>` : "";
  const note = f.note ? `<div class="note-m">${esc(f.note)}</div>` : "";
  const pub = f.published || "—(omitted)";
  const truth = f.scan_truth || "—(extra in published)";
  const sel = d => v.decision===d ? "sel" : "";
  return `<div class="card ${v.decision?'resolved':''}" data-id="${id}">
    <div class="tags">
      <span class="v ${f.verdict}">${f.verdict}</span>${two}
    </div>
    <div class="ctx">${ctxHTML(f)}</div>
    <div class="pair">
      <span class="lab">published</span><span class="frag pub">${esc(pub)}</span>
      <span class="arrow">→</span>
      <span class="lab">scan reads</span><span class="frag truth">${esc(truth)}</span>
    </div>
    ${blind}${note}
    <div class="dec">
      <button data-d="apply" class="${sel('apply')}">✓ Correct to scan</button>
      <button data-d="keep" class="${sel('keep')}">✗ Keep published</button>
      <button data-d="custom" class="${sel('custom')}">✎ Neither…</button>
      <button data-d="skip" class="${sel('skip')}">? Skip</button>
    </div>
    <div class="custom ${v.decision==='custom'?'show':''}">
      <input type="text" placeholder="true reading…" value="${esc(v.custom||'')}" data-custom>
    </div>
    <textarea class="notes" placeholder="note (optional)…" data-note>${esc(v.note||'')}</textarea>
  </div>`;
}

function render(){
  const main = document.getElementById("main");
  let total=0, done=0, html="";
  for(const pg of DATA){
    const fs = pg.findings.filter(matches);
    total += pg.findings.length;
    const pgdone = pg.findings.filter(f=>(store[fid(f)]||{}).decision).length;
    done += pgdone;
    if(!fs.length) continue;
    const harv = pg.harvard_page
      ? `Harvard: PDF p.${pg.harvard_page} (${pg.harvard_res})`
      : "Harvard: no counterpart leaf";
    html += `<details class="page" open>
      <summary>
        <span class="pg">p.${pg.page}</span>
        <span class="meta">${pg.findings.length} finding${pg.findings.length>1?'s':''} &middot; ${harv}</span>
        <span class="done">${pgdone}/${pg.findings.length} done</span>
      </summary>
      <div class="body">
        <div class="scanwrap"><div class="scan">
          <img src="${pg.img}" loading="lazy" alt="LoC scan p.${pg.page}" data-zoom="${pg.img}">
          <a href="${pg.img}" target="_blank">open full scan ↗</a>
          <div class="harv">${harv} &middot; native-resolution LoC shown</div>
        </div></div>
        <div class="cards">${fs.map(card).join("")}</div>
      </div>
    </details>`;
  }
  main.innerHTML = html || "<p style='color:#6f685c'>Nothing matches this filter.</p>";
  document.getElementById("ndone").textContent = Object.values(store).filter(v=>v.decision).length;
  document.getElementById("ntot").textContent = total;
}

document.addEventListener("click", e=>{
  const z = e.target.closest("[data-zoom]");
  if(z){ document.getElementById("zoomimg").src = z.dataset.zoom;
         document.getElementById("zoom").showModal(); return; }
  if(e.target.id==="zoomimg" || e.target.closest("dialog.zoom") && e.target.tagName!=="IMG"){
    document.getElementById("zoom").close(); return; }
  const b = e.target.closest(".dec button");
  if(b){
    const id = b.closest(".card").dataset.id;
    const d = b.dataset.d;
    store[id] = store[id] || {};
    store[id].decision = (store[id].decision===d) ? null : d;
    save(); return;
  }
  const chip = e.target.closest(".chip");
  if(chip){
    filter = chip.dataset.f;
    document.querySelectorAll(".chip").forEach(c=>c.classList.toggle("on",c===chip));
    render(); return;
  }
});
document.getElementById("zoom").addEventListener("click", e=>{
  if(e.target.id==="zoom") e.target.close();
});
document.addEventListener("input", e=>{
  const card = e.target.closest(".card"); if(!card) return;
  const id = card.dataset.id; store[id] = store[id] || {};
  if(e.target.matches("[data-custom]")) store[id].custom = e.target.value;
  if(e.target.matches("[data-note]"))   store[id].note   = e.target.value;
  localStorage.setItem(KEY, JSON.stringify(store));
});
document.getElementById("export").addEventListener("click", ()=>{
  const out = [];
  for(const pg of DATA) for(const f of pg.findings){
    const v = store[fid(f)] || {};
    out.push({page:f.page, oidx:f.oidx, verdict_machine:f.verdict,
      published:f.published, scan_truth:f.scan_truth, copy:f.copy,
      decision:v.decision||null, custom:v.custom||null, note:v.note||null});
  }
  const blob = new Blob([JSON.stringify({generated_from:"sample_estimate", findings:out}, null, 2)],
    {type:"application/json"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "misread_audit_results.json";
  a.click();
});

render();
</script>
</body></html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--misreads-only", action="store_true",
                    help="exclude spelling 'variant' findings")
    args = ap.parse_args()
    wanted = {"misread"} if args.misreads_only else {"misread", "variant"}
    pages = collect(wanted)
    n = sum(len(p["findings"]) for p in pages)
    OUT.write_text(PAGE_TMPL.replace("__DATA__", json.dumps(pages, ensure_ascii=False)),
                   encoding="utf-8")
    print(f"{n} findings across {len(pages)} pages -> {OUT}")


if __name__ == "__main__":
    main()
