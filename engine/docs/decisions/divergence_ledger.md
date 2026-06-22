# Divergence Ledger

> Deliberate **behavioral** changes from PLL — never silent. Append-only. See
> `engine/docs/port_discipline.md` §2, §5.
>
> **No entries yet.** The ledger opens at the first behavioral divergence (expected during M3
> porting). Until then this file pins the format only.
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
