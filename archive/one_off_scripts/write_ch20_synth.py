#!/usr/bin/env python3
outpath = "/Users/ben_mpa/Desktop/Per la liberta/state/translations/p1_capitolo_ventesimo.md"
text = """\
<!-- pages:98-100 -->

## Chapter Twenty

WHAT I am about to narrate I gathered from the letters Giustiniano wrote to me. I have them impressed upon my memory in indelible characters. To hearten mother, Giustiniano would sketch the situation for her, tempering it with a good dose of optimism. Luisa would undergo some interrogations, but would soon be set at liberty. Father had the reputation of an old patriot, an irreducible man, and would not have been able to extricate himself so easily. But how could they condemn him without proof? The judicial authorities were rigorous beyond all telling; but they were keen to appear most upright and would not dare commit a manifest piece of knavery. As for me, he himself had accompanied me as far as the mines of Agordo. From that point, I had chosen paths that only I and the chamois knew how to travel. I must have already arrived beyond the frontier, yet the Police still believed me to be in Belluno and were searching for me there. Before long, they would receive letters from me from Switzerland, or from some other country where the yellow and black did not fly. Everything therefore depended on not losing heart, so as to preserve one\u2019s health, so necessary in that storm.

But the confidence he laboured to instil in mother\u2019s heart was far from dwelling in his own. The newspapers, subject to rigorous censorship, seemed agreed in treating the latest conspiracy with the conspiracy of silence. Yet news knows how to travel a great distance even without the aid of newspapers. Now from the lips of trusted friends he encountered along the way; now at the caf\u00e9, gathered about a table, between one remark about the fine weather and another about the price of agricultural produce, words that could not be openly spoken without danger would slip into his ear, and from them, as always in such cases, the hopeful assurances appeared but faintly delineated, while the sinister predictions were painted in bold strokes.

One evening, these seemed to have found, in the facts, a tragic fulfilment. \u201cAmong the gorges of the Alps, a patrol had barred the path of the fugitive patriot... the order to surrender set at naught... the noble heart shattered by Austrian lead... the series of generous impulses cut short for ever. That very night, the body would arrive in Belluno for the legal formalities.\u201d

Giustiniano hastened home to prevent the sorrowful news from reaching mother through some incautious mouth. He found her abed. Wake her? To what purpose?

She would have more than enough time to weep. He paced the room back and forth until a very late hour; then, overcome by weariness, he let himself fall into an armchair and fell asleep.

Through the half-closed shutters, the first light of dawn was barely peering in, and already mother, impatient for news, was bringing him his customary cup of coffee. She saw him and, divining the sleepless and anguished night he had passed, instead of waking him, she went to the untouched bed, took a blanket from it, and spread it over his knees and chest. Just then, the bell rang furiously.

Giustiniano awoke with a start, saw, remembered, understood. He threw his arms about the poor woman\u2019s neck and said to her:

\u201cMamma, my poor mamma, be strong and prepare yourself for the worst.\u201d

They departed in a carriage, a gendarme on the box, an inspector at their side. No fits of hysteria, no sobbing, no silent tears. Giustiniano held fast to the right hand of the grieving woman, who paid him no heed, who remained motionless, her gaze fixed upon some distant point perceptible to her alone.

She was led into a large, cold room. From the opposite wall a plank projected, its far end resting upon a trestle; upon the plank a sheet was spread; beneath the sheet, with sinister uncertainty, the forms of a man in the rigidity of death were outlined. A soldier, rifle at the order, stood erect and stiff-chested beside it. Another, in a simple waistcoat, his sleeves rolled back, his left hand plunged deep into a large boot upon which his eyes were intently fixed, was furiously working the brush and polishing away at it. Four officers, arranged in a circle, were conferring in low voices. A blazing brazier adulterated, with its ruddy glare, the limpid light of morning.

At mother\u2019s entrance, the officers broke off their conversation and turned their faces toward that severe apparition, which advanced to the foot of the corpse with a firm, almost resolute step.

Someone spoke. He alluded to the painful necessity imposed upon him by duty and lamented the untimely end of the misguided who lay hands upon the sacred majesty of the Law... She seemed not to hear; her whole soul was concentrated in her eyes, which blazed beneath the black veil.

There was one who drew back the sheet with a sudden gesture. A livid face appeared. Then a single sob resounded in the sepulchral silence \u2014 one only!... but it sufficed to resolve the tempest of a heart.

Mamma lifted her veil, gazed intently upon the officers, and in a voice in which throbbed the muffled menace of an entire People, said: \u201cNo, this poor wretch is not my son! Carletto lives!... he lives, and he will avenge the anguish I have suffered, and he will avenge his Country!\u201d

In the general stupefaction, maternal majesty had its triumph. She moved toward the door with as firm a step as that with which she had come. The soldier in his waistcoat blew warm breath upon the boot and laid on with the brush more furiously than ever... perhaps at that moment he wished that the barracks and the Empire were concentrated in that muddy upper leather. The stiff-chested soldier beside the corpse did not stir an eyelid... an automaton in uniform, he awaited a command that did not come.

The four officers, having turned suddenly pale, had their thoughts perhaps dragged by force to a distant country, beyond the Alps, where other mothers were suffering.

Into the cold surroundings of the barracks, into breasts hardened by iron discipline, accustomed to the fierce emotions of arrogance and of blood, there evidently crept the gentle remembrances of childhood, and reawakened within them the stunned pity. For a moment, the despot\u2019s minions became once more men of the People. The severe apparition \u2014 unmolested, admired \u2014 vanished!
"""
with open(outpath, 'w', encoding='utf-8') as f:
    f.write(text)
print("Written successfully.")
