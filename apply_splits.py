r"""Apply the 15 confident panel-split closes (scan-read + dictionary oracle).
11 restores (adopt the page form) + 4 keeps (no edit). Anchored + verified.
The 12 editorial splits and 4 re-box splits are left untouched.
"""
import json
from pathlib import Path
IT=Path("output/italian_clean.md")
CLS=Path("data/blind_deviations_classified.json")

RESTORE=[  # id, old (anchored), new
 (72,  "Il 8 Giugno",                      "Il 3 Giugno"),
 (88,  "pur non odiandomi,",               "pur non odiandosi,"),
 (116, "sino a Langres, la località",      "sino a Langre, la località"),
 (117, "albergo di Langres e già",         "albergo di Langre e già"),
 (322, "i candelieri ne traballarono",     "i candellieri ne traballarono"),
 (335, "egli, amante del ",                "egli, Argante "),
 (417, "a raggiungere le ardue vette",     "a raggiugere le ardue vette"),
 (576, "d'altronde, nel mio diniego",      "d'altronde, quel mio diniego"),
 (655, "e le compariva, su una specie",    "e le compartiva, su una specie"),
 (687, 'semplice parola "fondali!" mi',    'semplice parola "sfondali!" mi'),
 (778, "la Presidenza di Pio IX",          "la Presidenzia di Pio IX"),
]
KEEP=[381,614,698,829]   # no edit; edition is correct

DUP_OK={655}   # #655's sentence is duplicated in the derived text; fix the word in both copies
t=IT.read_text(encoding="utf-8"); ok=True
for i,o,n in RESTORE:
    c=t.count(o); good = c==1 or (i in DUP_OK and c>=1)
    print(f"#{i:>3} count={c}  {'OK' if good else '<<<'}  {o[:45]!r}->{n[:45]!r}")
    if not good: ok=False
assert ok, "ABORT: non-unique anchor"
for i,o,n in RESTORE: t=t.replace(o,n)   # replace all (count==1 for all but #655)
IT.write_text(t,encoding="utf-8"); print("\nwrote",IT)

rep=json.loads(CLS.read_text(encoding="utf-8"))
rmap={i:(o,n) for i,o,n in RESTORE}
for it in rep["items"]:
    i=it["id"]
    if i in rmap:
        it["resolved"]="applied"; it["action"]="restore"
        it["applied_edit"]={"old":rmap[i][0],"new":rmap[i][1]}
        it["reason"]="panel split resolved by native-res scan + 3-dict oracle: page prints the restored form"
    elif i in KEEP:
        it["resolved"]="applied"; it["action"]="keep"
        it["reason"]="panel split resolved by native-res scan + 3-dict oracle: edition correct (page form is non-word typo / no real deviation)"
CLS.write_text(json.dumps(rep,ensure_ascii=False,indent=2),encoding="utf-8")
print("marked 15 resolved (11 restore + 4 keep)")
