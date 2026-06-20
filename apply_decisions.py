r"""Apply the worked deviation-review decisions to output/italian_clean.md and mark
them resolved in data/blind_deviations_classified.json so they drop from the sheet.

Every IT edit below is anchored to unique context and verified to occur exactly the
expected number of times before anything is written. Scan-confirmed against the 1913
page images. EN meaning-changers are handled separately.

    uv run python apply_decisions.py --dry-run
    uv run python apply_decisions.py
"""
import argparse, json
from pathlib import Path

ROOT = Path(".")
IT = ROOT/"output"/"italian_clean.md"
CLASSIFIED = ROOT/"data"/"blind_deviations_classified.json"

# (id, old, new) — IT text edits. old must be unique in the file.
EDITS = [
 # --- simple restores (period spelling / misread / variant), scan-confirmed ---
 (0,   "a cui la tisi rode",                 "a cui l'etisia rode"),
 (17,  "La famiglia Nosaidana vanta",        "La famiglia Nosadana vanta"),
 (20,  "le mie birichinate che",             "le mie biricchinate che"),
 (85,  "poi a Tarragona. Il Trolli",         "poi a Terragona. Il Trolli"),
 (199, "suo amanuense, certo Bardini",       "suo ammanuense, certo Bardini"),
 (219, "un esiguo colpo di militi",          "un esiguo corpo di militi"),
 (228, "Sui baluardi, ventidue nostri",      "Sui baluardi, diventati nostri"),
 (379, "nella Transilvania, venne",          "nella Transylvania, venne"),
 (462, "Sorrise tristemente e,",             "Sorrise tristamente e,"),
 (540, "tanto celermente che le guardie",    "tanto celeramente che le guardie"),
 (619, "il sole californese, vicino",        "il sole californiese, vicino"),
 (635, "l'ultima Tuie. Più studiavo",        "l'ultima Tule. Più studiavo"),
 (697, "da impiegarci un paio di mesi",      "da impiegarvi un paio di mesi"),
 (768, "dal Le Houx, l'ex galeotto",         "dal Le Roux, l'ex galeotto"),
 (803, "ferite inflittale dalla belva",      "ferite inflittele dalla belva"),
 (691, "all'isola del bagnato baciato la fregata", "all'isola del Saluto la fregata"),
 (84,  "Era morto un repubblicano di grido", "Era morto *** repubblicano di grido"),
 # --- unsures, resolved by scan ---
 (140, "villa Corsini) e a quel Winkler",    "villa Corsini) ed a quel Winkler"),
 (216, "si stende un parapetto al così che", "si stende un parapetto alto così che"),
 (749, "nelle alberatura uscenti",           "nelle alberature uscenti"),
 # --- restore plural (#194), keep edition quote glyphs ---
 (194, 'colle "blouse"? Non',                'colle "blouses"? Non'),
 # --- ellipsis-as-restore (page prints suspension points, edition guessed a word) ---
 (135, "del mondo romano buon al livello",   "del mondo romano... al livello"),
 # --- dittographies: page has each phrase ONCE; remove the OCR duplication ---
 (4,   '"Entri! Entri, entri!',              '"Entri, entri!'),
 (11,  '"Giorni felici, giorni felici... tramontati', '"Giorni felici... tramontati'),
 (33,  "altro sangue... sangue... ma ripercuotono",   "altro sangue... ma ripercuotono"),
 (74,  "Fra quel caos,\n\nFra quel caos, inciampo",   "Fra quel caos, inciampo"),
 (487, "Mi salutò con\n\nMi salutò con una poderosa", "Mi salutò con una poderosa"),
 (616, '"La scommessa! La scommessa!... avete',       '"La scommessa!... avete'),
 (760, "Calunniate, calunniate, calunniate ecc.",     "Calunniate, calunniate ecc."),
 (83,  "Bersaglieri. Rifiutai! Perchè? Rifiutai!\n\nPerchè?\n\nLe subitanee",
       "Bersaglieri... Rifiutai! Perchè? Le subitanee"),
 (302, "di vita. Un contrabbandiere.\n\nUn contrabbandiere — pensai —",
       "di vita... Un contrabbandiere — pensai —"),
 # --- flags: corrected fix (scan-confirmed) ---
 (218, "lasciato senza guardia; custodia dell'edificio",
       "lasciato senza guardie. A custodia dell'edificio"),
 (224, "bambinaie e di birichini. Regola",   "bambinaie e di biricchini. Regola"),
 (690, "tu possa murì... muri ammazzato!",   "tu possa.... murì amazzato!"),
]
# decided but NO text edit (edition already correct / non-issue / deferred to ellipsis pass)
NOEDIT = {
 2,25,27,139,205,208,212,214,215,  # keep — edition correctly fixed source typo
 29,    # flag — "Vittorio Emanuele 1. L'Austria" is correct as published (bogus finding)
 493,   # ellipsis dot-count already restored by restore_ellipses.py (stale finding)
 144,   # flag — finding mispoints; real divergence is an ellipsis case, deferred per user
}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--dry-run",action="store_true")
    a=ap.parse_args()
    txt=IT.read_text(encoding="utf-8")
    ok=True
    for i,old,new in EDITS:
        n=txt.count(old)
        flag="" if n==1 else "  <<< NOT UNIQUE"
        if n!=1: ok=False
        print(f"#{i:>3} count={n}{flag}  {old[:50]!r} -> {new[:50]!r}")
    decided_ids={i for i,_,_ in EDITS}|NOEDIT
    print(f"\nedits={len(EDITS)}  no-edit={len(NOEDIT)}  total decided handled={len(decided_ids)}")
    if not ok:
        print("\nABORT: some anchors not unique — fix table before applying."); return
    if a.dry_run:
        print("\n--dry-run: nothing written"); return
    for i,old,new in EDITS:
        txt=txt.replace(old,new,1)
    IT.write_text(txt,encoding="utf-8")
    print(f"\nwrote {IT}")
    # mark resolved in classified
    rep=json.loads(CLASSIFIED.read_text(encoding="utf-8"))
    edit_map={i:(old,new) for i,old,new in EDITS}
    res=0
    for it in rep["items"]:
        if it["id"] in decided_ids:
            it["resolved"]="applied"
            if it["id"] in edit_map:
                it["applied_edit"]={"old":edit_map[it["id"]][0],"new":edit_map[it["id"]][1]}
            res+=1
    CLASSIFIED.write_text(json.dumps(rep,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"marked {res} items resolved -> {CLASSIFIED}")

if __name__=="__main__": main()
