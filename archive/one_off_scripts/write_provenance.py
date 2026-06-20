import json, pathlib

provenance = {
    "primary_draft": "draft_claude__sonnet.md",
    "incorporations": [
        {
            "paragraph": 1,
            "from_draft": "draft_gemini__pro.md",
            "original": "to whom you owe the duty of leaving intact the good name you received from your father",
            "replacement": "to whom you must leave, in all its entirety, the good name you received from your father",
            "reason": "Gemini preserves the Italian 'in tutta la sua interezza' which Claude paraphrased away; the source specifically emphasises totality/completeness of the legacy."
        },
        {
            "paragraph": 4,
            "from_draft": "draft_gemini__pro.md",
            "original": "for his descendants",
            "replacement": "for his great-nephews",
            "reason": "'Pronipoti' in context means great-nephews (the great-uncle's relationship to di Rudio's generation), not the generic 'descendants'. Gemini's rendering is more precise."
        },
        {
            "paragraph": 7,
            "from_draft": "draft_gemini__pro.md",
            "original": "white hairs rendered venerable",
            "replacement": "hoary heads rendered venerable",
            "reason": "'Canizie' specifically denotes hoariness. 'Hoary heads' is more literary, more precise, and period-appropriate than 'white hairs'."
        },
        {
            "paragraph": 23,
            "from_draft": "draft_gemini__pro.md",
            "original": "the game of the little tyrants",
            "replacement": "the game of the petty tyrants",
            "reason": "'Petty tyrants' is the established English idiom for 'tirannelli' and reads more naturally than the literal 'little tyrants'."
        },
        {
            "paragraph": 30,
            "from_draft": "draft_gemini__pro.md",
            "original": "for the suppressed groans reverberating within its walls",
            "replacement": "for the groans suppressed by its walls",
            "reason": "The Italian 'gemiti repressi dalle sue mura' means groans suppressed BY the walls, not groans reverberating within. Gemini's reading is more faithful."
        },
        {
            "paragraph": 32,
            "from_draft": "draft_gemini__pro.md",
            "original": "sucked dry and corroded",
            "replacement": "emaciated and corroded",
            "reason": "'Smunta' means emaciated/gaunt, not 'sucked dry' which is more colloquial. 'Emaciated' maintains the literary register."
        },
        {
            "paragraph": 38,
            "from_draft": "draft_gemini__pro.md",
            "original": "Hallowed by the feverish hand",
            "replacement": "Sanctified by the feverish hand",
            "reason": "'Santificati' directly translates to 'sanctified'; preserves the explicit religious register of the original."
        }
    ],
    "edgren_influences": [
        {
            "italian_word": "lembo",
            "edgren_definition": "extremity, limit",
            "english_choice": "uttermost extremity",
            "paragraph": 4,
            "note": "Edgren defines 'lembo' as 'extremity, limit'. Combined with 'estremo' in the source, 'uttermost extremity' captures both words precisely, preferred over 'strip' or 'border'."
        },
        {
            "italian_word": "interezza",
            "edgren_definition": "(strength); integrity",
            "english_choice": "in all its entirety",
            "paragraph": 1,
            "note": "Edgren gives 'integrity' and '(strength)' for 'interezza'. The source 'in tutta la sua interezza' means completeness. 'Entirety' preserves this sense."
        },
        {
            "italian_word": "movente",
            "edgren_definition": "moving; M.: motive",
            "english_choice": "motive",
            "paragraph": 1,
            "note": "Edgren confirms 'motive' as the noun sense of 'movente', supporting 'historical motive'."
        },
        {
            "italian_word": "memoria",
            "edgren_definition": "memory (remembrance); imparare a memoria, learn by heart",
            "english_choice": "commit to memory",
            "paragraph": 4,
            "note": "Edgren includes 'imparare a memoria, learn by heart'. 'Commit to memory' was preferred as slightly more formal."
        },
        {
            "italian_word": "scanso",
            "edgren_definition": "avoiding (shunning)",
            "english_choice": "to forestall",
            "paragraph": 1,
            "note": "Edgren defines 'scanso' as 'avoiding (shunning)'. 'Forestall' was chosen over plain 'avoid' for its more elevated register."
        }
    ]
}

out = pathlib.Path('state/multi_drafts/p1_capitolo_secondo/provenance.json')
out.write_text(json.dumps(provenance, indent=2, ensure_ascii=False))
print("Provenance written to", out)
