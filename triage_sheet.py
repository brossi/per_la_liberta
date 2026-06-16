"""Render the comprehension ledger as a human-review triage sheet (HTML).

Stage 1 of the intention-review track collects suspicion clusters into
state/comprehension/flags.jsonl. This turns that machine output into the surface
a human adjudicates on: each cluster shown with its [prev/target/next] review
window (the anchor highlighted in the target), the per-model rationales grouped
by architecture, and a verdict control.

The verdict taxonomy comes from calibrating the breadth-3/high tier (see the
project notes): comprehension failures split into two remediation tracks —
re-translate (the English is wrong) vs gloss (the English is faithful but the
allusion is opaque) — plus recoverable (real but minor), dismiss (false
positive: split-sentence artifact or intentional device), and unsure (needs the
source — defer to the bilingual pass). Verdicts persist in the browser's
localStorage and export to JSON; nothing here writes back to the corpus.

    uv run python triage_sheet.py                 # default actionable scope
    uv run python triage_sheet.py --breadth 1     # include singletons too
    uv run python triage_sheet.py --min-score 40  # only the hottest clusters
    uv run python triage_sheet.py --top 200       # cap at N highest-scoring
"""

import argparse
import html
import json
import os

from comprehension import OUT_DIR, build_units, resolve_anchor

FLAGS = os.path.join(OUT_DIR, "flags.jsonl")
SHEET = os.path.join(OUT_DIR, "triage.html")

# Terminal punctuation a complete passage is expected to end on. A target that
# ends otherwise is likely a sentence split across the passage boundary — the
# one false-positive class calibration surfaced (e.g. "...Like a Minos who").
_TERMINAL = '.!?…"»\'’)'


def load_clusters() -> list[dict]:
    return [json.loads(l) for l in open(FLAGS, encoding="utf-8")]


def maybe_split(target: str) -> bool:
    t = (target or "").rstrip()
    return bool(t) and t[-1] not in _TERMINAL


def highlight(target: str, anchor: str) -> str:
    """Escape the target and wrap the anchor occurrence in <mark>, if it resolves."""
    off = resolve_anchor(anchor, target)
    if off < 0:
        return html.escape(target)
    end = off + len(anchor)
    return (html.escape(target[:off]) + "<mark>" + html.escape(target[off:end])
            + "</mark>" + html.escape(target[end:]))


def scope(clusters: list[dict], args) -> list[dict]:
    rows = [c for c in clusters if c["breadth"] >= args.breadth and c["score"] >= args.min_score]
    rows.sort(key=lambda c: c["score"], reverse=True)
    return rows[: args.top] if args.top else rows


def build(rows: list[dict]) -> list[dict]:
    """Join each cluster to its review window and shape it for the page."""
    units = {(u["chapter"], u["idx"]): u for u in build_units()}
    out = []
    for rank, c in enumerate(rows, 1):
        u = units.get((c["chapter"], c["idx"]), {})
        target = u.get("target", "")
        # one rationale entry per model read, newest model grouping preserved
        rats = [{"model": r["model"].split("-")[0], "sev": r["severity"],
                 "cat": r["category"], "why": r["why"]} for r in c.get("rationales", [])]
        out.append({
            "id": f'{c["chapter"]}::{c["idx"]}::{c["anchor"][:48]}',
            "rank": rank, "score": c["score"], "breadth": c["breadth"],
            "severity": c["severity"], "category": c["category"],
            "chapter": c["chapter"], "title": c.get("title", ""), "idx": c["idx"],
            "anchor": c["anchor"], "split": maybe_split(target),
            "prev": u.get("prev") or "", "target_html": highlight(target, c["anchor"]),
            "next": u.get("next") or "", "rationales": rats,
        })
    return out


PAGE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Comprehension triage — Per la Libertà</title>
<style>
:root{
 --bg:#f7f5f0; --card:#fff; --ink:#1c1a17; --mut:#6b6359; --line:#e2dccf;
 --mark:#ffe8a3; --hi:#b8472a; --high:#c0392b; --med:#c87f0a; --low:#7a8b6f;
 --rt:#8e44ad; --gl:#2a6b8e; --rec:#7a8b6f; --dis:#999; --uns:#c87f0a;
}
*{box-sizing:border-box}
body{margin:0;font:16px/1.55 Georgia,'Spectral',serif;background:var(--bg);color:var(--ink)}
header{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line);
 padding:.6rem 1rem;box-shadow:0 2px 6px rgba(0,0,0,.04)}
h1{font:600 1.15rem/1.2 Georgia,serif;margin:0 0 .35rem}
.bar{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center;font-size:.82rem}
.bar select,.bar input{font:inherit;font-size:.82rem;padding:.18rem .35rem;border:1px solid var(--line);
 border-radius:4px;background:#fff}
.stat{color:var(--mut)}
.wrap{max-width:60rem;margin:1rem auto;padding:0 1rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;margin:0 0 1rem;
 padding:.85rem 1rem;box-shadow:0 1px 3px rgba(0,0,0,.04)}
.meta{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center;font-size:.78rem;color:var(--mut);margin-bottom:.5rem}
.pill{padding:.05rem .45rem;border-radius:999px;border:1px solid var(--line);background:#faf8f3;white-space:nowrap}
.sev-high{color:#fff;background:var(--high);border-color:var(--high)}
.sev-medium{color:#fff;background:var(--med);border-color:var(--med)}
.sev-low{color:#fff;background:var(--low);border-color:var(--low)}
.b3{font-weight:700;color:var(--hi)}
.split{color:#fff;background:#555;border-color:#555}
.loc{font-weight:600;color:var(--ink)}
.win p{margin:.35rem 0}
.win .ctx{color:var(--mut);font-size:.9rem}
.win .tgt{background:#fffdf6;border-left:3px solid var(--mark);padding:.3rem .6rem;border-radius:0 4px 4px 0}
mark{background:var(--mark);padding:0 .1em;border-radius:2px}
details.rats{margin:.5rem 0 0}
details.rats>summary{cursor:pointer;font-size:.8rem;color:var(--mut)}
.rat{font-size:.85rem;margin:.4rem 0;padding-left:.6rem;border-left:2px solid var(--line)}
.rat b{font-variant:small-caps;color:var(--mut);font-weight:600}
.verdict{display:flex;flex-wrap:wrap;gap:.3rem;margin:.6rem 0 0;align-items:center}
.verdict label{font-size:.78rem;padding:.18rem .5rem;border:1px solid var(--line);border-radius:999px;
 cursor:pointer;user-select:none;background:#faf8f3}
.verdict input{display:none}
.verdict input:checked+span{font-weight:700}
label.v-retranslate input:checked~*,label.v-retranslate:has(:checked){box-shadow:inset 0 0 0 2px var(--rt)}
label.v-gloss:has(:checked){box-shadow:inset 0 0 0 2px var(--gl)}
label.v-recoverable:has(:checked){box-shadow:inset 0 0 0 2px var(--rec)}
label.v-dismiss:has(:checked){box-shadow:inset 0 0 0 2px var(--dis)}
label.v-unsure:has(:checked){box-shadow:inset 0 0 0 2px var(--uns)}
.note{width:100%;margin-top:.5rem;font:inherit;font-size:.85rem;padding:.35rem .5rem;
 border:1px solid var(--line);border-radius:4px;resize:vertical;min-height:2.2rem}
.card.done{opacity:.62}
.btn{font:inherit;font-size:.8rem;padding:.2rem .6rem;border:1px solid var(--line);border-radius:5px;
 background:#fff;cursor:pointer}
.btn:hover{background:#f0ece2}
.hidden{display:none}
</style></head><body>
<header>
 <h1>Comprehension triage <span class="stat" id="hcount"></span></h1>
 <div class="bar">
  <input id="q" type="search" placeholder="search text / rationale…" style="min-width:12rem">
  <select id="fcat"></select><select id="fsev"></select><select id="fbrd"></select>
  <select id="fch"></select><select id="fverd"></select>
  <label class="stat"><input type="checkbox" id="fsplit"> split-only</label>
  <span style="flex:1"></span>
  <span class="stat" id="prog"></span>
  <button class="btn" id="exportBtn">Export verdicts</button>
  <button class="btn" id="importBtn">Import</button>
  <input type="file" id="file" accept="application/json" class="hidden">
 </div>
</header>
<div class="wrap" id="list"></div>
<script>
const DATA = __DATA__;
const KEY = "pll-triage-verdicts";
const VS = [["retranslate","re-translate"],["gloss","gloss/footnote"],
 ["recoverable","recoverable"],["dismiss","dismiss (FP)"],["unsure","unsure — check source"]];
let V = JSON.parse(localStorage.getItem(KEY) || "{}");
function save(){localStorage.setItem(KEY, JSON.stringify(V));}

function opt(sel, items, label){
 sel.innerHTML = `<option value="">${label}</option>` +
  items.map(v=>`<option value="${v}">${v}</option>`).join("");
}
const uniq = k => [...new Set(DATA.map(d=>d[k]))];
opt(fcat, uniq("category").sort(), "category: all");
opt(fsev, ["high","medium","low"], "severity: all");
opt(fbrd, [3,2,1], "breadth: all");
opt(fch, uniq("chapter").sort(), "chapter: all");
opt(fverd, ["(none)","retranslate","gloss","recoverable","dismiss","unsure"], "verdict: all");

function card(d){
 const v = V[d.id] || {};
 const rats = d.rationales.map(r=>
  `<div class="rat"><b>${r.model}</b> · ${r.sev}/${r.cat} — ${esc(r.why)}</div>`).join("");
 const verds = VS.map(([val,lab])=>
  `<label class="v-${val}"><input type="radio" name="v-${d.id}" value="${val}"
    ${v.verdict===val?"checked":""}><span>${lab}</span></label>`).join("");
 return `<div class="card${v.verdict?' done':''}" data-id="${d.id}">
  <div class="meta">
   <span class="pill ${d.breadth===3?'b3':''}">b${d.breadth}/3</span>
   <span class="pill sev-${d.severity}">${d.severity}</span>
   <span class="pill">${d.category}</span>
   <span class="pill">score ${d.score}</span>
   ${d.split?'<span class="pill split">⚠ possible split</span>':''}
   <span class="loc">#${d.rank} · ${d.chapter} ¶${d.idx}</span>
  </div>
  <div class="win">
   ${d.prev?`<p class="ctx">${esc(d.prev)}</p>`:''}
   <p class="tgt">${d.target_html}</p>
   ${d.next?`<p class="ctx">${esc(d.next)}</p>`:''}
  </div>
  <details class="rats"><summary>${d.rationales.length} model reads</summary>${rats}</details>
  <div class="verdict">${verds}</div>
  <textarea class="note" placeholder="note (optional)…">${esc(v.note||"")}</textarea>
 </div>`;
}
function esc(s){return (s||"").replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));}

function render(){
 const q = qf.q.value.toLowerCase();
 const rows = DATA.filter(d=>{
  if(fcat.value && d.category!==fcat.value) return false;
  if(fsev.value && d.severity!==fsev.value) return false;
  if(fbrd.value && d.breadth!=+fbrd.value) return false;
  if(fch.value && d.chapter!==fch.value) return false;
  if(fsplit.checked && !d.split) return false;
  const vv = (V[d.id]||{}).verdict || "(none)";
  if(fverd.value && vv!==fverd.value) return false;
  if(q){
   const hay = (d.target_html+" "+d.prev+" "+d.next+" "+
    d.rationales.map(r=>r.why).join(" ")).toLowerCase();
   if(!hay.includes(q)) return false;
  }
  return true;
 });
 list.innerHTML = rows.map(card).join("") || '<p class="stat">No clusters match.</p>';
 hcount.textContent = `· ${rows.length} shown`;
 const done = DATA.filter(d=>(V[d.id]||{}).verdict).length;
 prog.textContent = `${done}/${DATA.length} judged`;
}
const qf = {q};
[q,fcat,fsev,fbrd,fch,fverd,fsplit].forEach(el=>el.addEventListener("input",render));

list.addEventListener("change",e=>{
 const card = e.target.closest(".card"); if(!card) return;
 const id = card.dataset.id; V[id] = V[id]||{};
 if(e.target.type==="radio") V[id].verdict = e.target.value;
 save();
 const done = DATA.filter(d=>(V[d.id]||{}).verdict).length;
 prog.textContent = `${done}/${DATA.length} judged`;
 card.classList.toggle("done", !!V[id].verdict);
});
list.addEventListener("input",e=>{
 if(!e.target.classList.contains("note")) return;
 const id = e.target.closest(".card").dataset.id;
 V[id] = V[id]||{}; V[id].note = e.target.value; save();
});

exportBtn.onclick=()=>{
 const out = DATA.filter(d=>V[d.id]).map(d=>({
  chapter:d.chapter, idx:d.idx, anchor:d.anchor, category:d.category,
  severity:d.severity, breadth:d.breadth, score:d.score, ...V[d.id]}));
 const blob = new Blob([JSON.stringify(out,null,2)],{type:"application/json"});
 const a = document.createElement("a");
 a.href = URL.createObjectURL(blob); a.download = "triage_verdicts.json"; a.click();
};
importBtn.onclick=()=>file.click();
file.onchange=async()=>{
 const txt = await file.files[0].text(); const arr = JSON.parse(txt);
 for(const r of arr){ const id = `${r.chapter}::${r.idx}::${r.anchor.slice(0,48)}`;
  V[id] = {verdict:r.verdict, note:r.note||""}; }
 save(); render();
};
render();
</script></body></html>"""


def main() -> None:
    ap = argparse.ArgumentParser(description="render the comprehension ledger as a triage sheet")
    ap.add_argument("--breadth", type=int, default=2, help="minimum breadth (default 2; 1 includes singletons)")
    ap.add_argument("--min-score", type=float, default=0.0, help="minimum suspicion score")
    ap.add_argument("--top", type=int, default=0, help="cap to N highest-scoring clusters (0 = no cap)")
    args = ap.parse_args()

    clusters = load_clusters()
    rows = build(scope(clusters, args))
    page = PAGE.replace("__DATA__", json.dumps(rows, ensure_ascii=False))
    open(SHEET, "w", encoding="utf-8").write(page)
    splits = sum(1 for r in rows if r["split"])
    print(f"clusters in sheet: {len(rows)}  (breadth>={args.breadth}, score>={args.min_score})")
    print(f"  flagged possible-split: {splits}")
    print(f"  sheet: {SHEET}")


if __name__ == "__main__":
    main()
