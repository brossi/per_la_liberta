r"""Auto-resolve the panel-split substitution deviations by reading the word inside
the red box on each native-resolution crop. Splits are objective transcription
questions (what does the 1913 page actually print), so a clean native-res read is
the right arbiter (project_vision_reviewer / vision_escalation_signal). Reports a
verdict + evidence per item; applies nothing — output is for review.

    uv run python resolve_splits.py
"""
import json, re, unicodedata, concurrent.futures as cf
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image
import vision_review as vr

ROOT=Path("."); load_dotenv(ROOT/".env")
CROPS=ROOT/"state"/"deviation_crops"
CLS=json.load((ROOT/"data"/"blind_deviations_classified.json").open(encoding="utf-8"))["items"]
MAN={r["id"]:r for r in json.load((CROPS/"manifest.json").open(encoding="utf-8"))}
splits=[it for it in CLS if (it.get("re_audit") or {}).get("consensus")=="split" and not it.get("resolved")]

SYS=("You read a small crop from a 1913 Italian book page at native resolution. A RED "
     "rectangle marks exactly one word. Transcribe that one boxed word EXACTLY as printed — "
     "every letter, accent, and any attached punctuation. Do not normalise, modernise, or "
     "guess; if a letter is genuinely illegible say so. Bodoni type: distinguish c/e, i/r, "
     "single vs double consonants, and word endings carefully.")

def core(s):
    s=unicodedata.normalize("NFC",(s or "").strip().lower())
    return re.sub(r"^[^0-9a-zà-ÿ']+|[^0-9a-zà-ÿ']+$","",s)
def deacc(s):
    return "".join(c for c in unicodedata.normalize("NFD",s) if unicodedata.category(c)!="Mn")

def read_word(it):
    m=MAN.get(it["id"],{})
    if not m.get("crop"): return it["id"],None,"NO-BOX",None
    p=CROPS/m["crop"]
    if not p.exists(): return it["id"],None,"NO-CROP",None
    jpeg=vr._jpeg(Image.open(p).convert("RGB"))
    user=('Transcribe ONLY the word inside the red rectangle, exactly as printed. '
          'Also give the few words around it. Reply ONLY JSON: '
          '{"boxed_word":"...","context":"...","legible":true|false}.')
    for _ in range(3):
        parsed,_=vr.read_json_images([("c",jpeg)],SYS,user,thinking="low")
        if isinstance(parsed,dict) and "boxed_word" in parsed:
            return it["id"],parsed.get("boxed_word"),parsed.get("context"),parsed.get("legible")
    return it["id"],None,"READ-FAIL",None

reads={}
with cf.ThreadPoolExecutor(max_workers=10) as ex:
    for fut in cf.as_completed([ex.submit(read_word,it) for it in splits]):
        i,w,ctx,leg=fut.result(); reads[i]=(w,ctx,leg)

rows=[]
for it in splits:
    w,ctx,leg=reads[it["id"]]
    pub,prn=it.get("published"),it.get("printed")
    cw,cpub,cprn=core(w or ""),core(pub),core(prn)
    if w is None: verdict,conf="needs-eye (no read)","-"
    elif cw==cpub and cw!=cprn: verdict,conf="KEEP",("high" if leg else "med")
    elif cw==cprn and cw!=cpub: verdict,conf="RESTORE",("high" if leg else "med")
    elif deacc(cw)==deacc(cpub) and deacc(cw)!=deacc(cprn): verdict,conf="KEEP","med (accent)"
    elif deacc(cw)==deacc(cprn) and deacc(cw)!=deacc(cpub): verdict,conf="RESTORE","med (accent)"
    else: verdict,conf="needs-eye (other)","-"
    rows.append((it["id"],it["page"],verdict,conf,pub,prn,w,ctx))

rows.sort(key=lambda r:(r[2],r[0]))
from collections import Counter
print("verdict tally:",dict(Counter(r[2].split(" ")[0] for r in rows)),"\n")
for i,pg,v,c,pub,prn,w,ctx in rows:
    print(f"#{i:>3} p.{pg:<3} {v:<18} {c:<12} pub={pub!r} prn={prn!r}  READ={w!r}")
    if v.startswith("needs-eye"): print(f"        ctx={ctx!r}")
# stash for an apply step
json.dump([{"id":i,"verdict":v,"conf":c,"read":w} for i,pg,v,c,pub,prn,w,ctx in rows],
          open("data/split_reads.json","w"),ensure_ascii=False,indent=2)
