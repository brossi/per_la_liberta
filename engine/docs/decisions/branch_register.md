# Branch Register

> Forks *seen and not taken*, and one-way-door decisions: the alternative, why passed now, and
> the revisit condition. A recorded passed-branch is **deferred, not lost.** Append-only.
> See `engine/docs/port_discipline.md` §4–§5. Deferral is never to save effort — only when
> intervening work resolves an open question the decision needs.

---

## BR-001 — adjudicate: own step vs. special case of the M6 oracle
- **Opened:** 2026-06-22 (M3 planning).
- **Context:** adjudicate's Zingarelli-only lookup is a special case of the planned M6 ≥2-of-N
  period-dictionary membership oracle.
- **Taken now:** port adjudicate's code in M3 behind a thin interface; keep Zingarelli-only and
  faithful.
- **Not taken:** re-express adjudicate on the general oracle now.
- **Why defer (information, not effort):** the oracle does not exist until M6; deciding now would
  commit blind. M6 builds it and is the point of maximum information.
- **Revisit:** M6, when the oracle exists. (See `ENGINE_M3_PLAN.md` D3.)

## BR-002 — non-Italian separability fixture: build now vs. after the language steps
- **Opened:** 2026-06-22 (governance review).
- **Context:** the synthetic book is Italian, so it tests structural injection, not language
  generalization; the language-axis seams (`word_score_accents`, consonant alphabet, period
  dictionaries) are untested for any non-Italian text.
- **Taken now:** defer; the limit is named in `port_discipline.md` §6.
- **Not taken:** build a non-Italian fixture now.
- **Why defer (information, not effort):** built now it would not know which seams to differ on
  and would pass trivially (the single-fixture blind spot). Porting the language-config-consuming
  steps resolves *what it must exercise*, so a later fixture is built to differ where it matters.
- **Revisit:** after the language-config-heavy steps are ported (M4b cleanup is the largest
  consumer); at the latest before M7 extraction, which claims portability.

## BR-003 — re-baseline-cites-ledger enforcement: automate now vs. review-enforce
- **Opened:** 2026-06-22 (governance review).
- **Context:** the anti-cheat rule (a `*_expected` golden change must cite a divergence or refresh
  entry) needs enforcement.
- **Taken now:** the rule is binding and **review-enforced** (human); stated in `port_discipline.md`
  §5.
- **Not taken:** build an automated check now.
- **Why defer (information, not effort):** no re-baseline workflow exists yet to enforce against;
  building the check now is speculative. M3 produces the first golden and the first possible
  re-baseline.
- **Revisit:** if/when re-baselines become frequent enough that human enforcement is unreliable
  (no earlier than M3's first re-baseline).
