# Divergence Ledger

> Deliberate **behavioral** changes from PLL — never silent. Append-only. See
> `engine/docs/port_discipline.md` §2, §5.
>
> **No entries yet.** The ledger opens at the first behavioral divergence; M2–M4a porting closed
> with none. The deliberate forks that did arise (e.g. adjudicate's result-envelope, BR-005) are
> orchestration/contract decisions recorded in the branch register, not ground-truth-licensed
> algorithm changes — the only kind this ledger admits. Until the first entry it pins the format only.
>
> A change to any `*_expected` golden fixture must cite an entry here **or** an input-refresh
> entry (a re-freeze of `books/<id>/inputs/` from the live tree — output changes, behavior does
> not). That is the anti-cheat rule (§5).

---

## Entry format

```
## DL-NNN — <short title>  (<date>, <step>)
- PLL did:        …
- We now do:      …
- Why better:     … + the ground truth that licenses it (scans / period dictionaries / review
                  findings) — never "feels cleaner" (port_discipline.md §2)
- Property test:  tests/…::test_…
- Golden:         <fixture>  (was … → now …)
```

## Input-refresh entry format

```
## RF-NNN — refreshed <inputs>  (<date>)
- Source:   live commit <sha>
- Re-froze: books/<id>/inputs/<files>
- Goldens regenerated:  <fixtures>   (input refresh, not a behavioral divergence)
```
