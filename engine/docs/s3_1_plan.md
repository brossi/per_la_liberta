# S3.1 — Zipf-cost DP word-segmentation + oracle-gating + boundary search (plan)

Status: **NOT YET SCOPED.** Tracker: `ENGINE_STRUCTURE_TASKS.md` line 430 (`BUILD`, `TODO`).
Dep: S3.0 (resource + normalization-policy lineage). Milestone S3, concern A.

This file is a **pre-scoping parking doc**: until S3.1 is planned in full, it accrues the questions and
decisions earlier tasks hand forward, so each is *deferred, not lost* (same discipline as
`decisions/branch_register.md`). When S3.1 is scoped, this grows into the full build spec.

The seam (`s3_0_plan.md` §1): **S3.0 = fold; S3.1 = tokenize + search.** S3.0 defined + versioned the
pre-lookup fold policy (`dictionaries/normalization.NormalizationPolicy` over `{case_fold, accent_fold}`)
and proved its `chunk_key`/`probe_forms` ops reproduce the live oracle fold path. S3.1 is the first
*production consumer*: the Zipf-cost DP word-segmenter over the frequency dictionary, the ≥2-of-3
period-dictionary oracle gate, the boundary-search predicate (`word_letter_class`), the tokenizer identity
(`spacy_model`), and the single canonical membership key (full-token fold) S3.0 deferred to here (D-F).

---

## Open questions carried in

### Q-S3.1-1 — `NormalizationPolicy` hashability when S3.1 keys/caches on a policy
- **Opened:** 2026-06-29 (S3.0.3 / #25 pre-commit adversarial audit, finding LOW-2).
- **Question:** `NormalizationPolicy` is a `@dataclass(frozen=True, slots=True)` with an `accent_fold: dict`
  field. A frozen dataclass auto-generates `__hash__`, but a `dict` field is unhashable, so `hash(policy)`
  raises `TypeError`. Acceptable, or should `accent_fold` become a hashable tuple-of-`(from, to)`-pairs
  (and/or the class be documented "not hashable")?
- **State at S3.0 (why not fixed now):** **harmless and convention-consistent.** Nothing hashes a policy —
  the lineage hashes `policy.descriptor()`'s *output* (a derived dict → canonical string), never
  `hash(policy)`, and no test puts a policy in a `set`/`dict`/`lru_cache`. It also matches the established
  config-layer convention: `LanguageProfile` / `OcrConfig` / `BookManifest` (`config/models.py`) are all
  `frozen=True, slots=True` with `dict` fields. The asymmetry with `ResourceLineage` (all `str`/`int`, so it
  stays hashable + `==`-deterministic, which invariant 6 relies on) is principled: the lineage is the
  persisted/versioned value object; the policy is an ephemeral op provider. Fixing it now would diverge from
  the `models.py` convention for no current consumer (YAGNI).
- **Revisit when:** S3.1's segmenter/oracle path **keys or caches on a `NormalizationPolicy`** — e.g.
  memoizing the fold per policy via `@lru_cache`, or holding policies in a `set`/`dict`. The unhashable
  field bites at the first `hash(policy)`.
- **Resolution options (decide against the real consumer):** (a) document "not hashable" and key the cache
  on a hashable surrogate (e.g. `_canonical(policy.descriptor())`, or the `(case_fold, accent_fold-as-tuple)`
  pair); (b) model `accent_fold` as a tuple-of-pairs so the frozen dataclass is genuinely hashable. Pairs
  with `s3_0_plan.md` D-F (the policy's op/descriptor contract) and S3.0's deferral of the canonical
  membership key.
