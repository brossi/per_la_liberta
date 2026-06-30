# S3.0 — resource + normalization-policy loading/versioning (build plan)

Status: **RATIFIED — ready to build (red-first).** Task `S3.0` (#19), milestone S3, concern A, wave W1.
Spec refs: ENGINE_STRUCTURE_PLAN §3.0, §3.6; D14, D21; `feedback_engine_agnostic`.
Dep S0.1 (`structure/artifacts.py` skeleton) — DONE.

This is the consolidated build spec. The full audit trail that produced it — a 12-point adversarial
review plus three follow-up rounds (2026-06-29) — lives in `s3_0_plan_discussion.md`; this document
states only the *settled* positions. Where a position was reached by overturning an earlier draft,
the discussion doc carries the reasoning.

---

## 1. Scope & boundaries

Tracker done-when (line 429): *"resources + normalizer load via the profile; both hashes enter
lineage; neutrality tier green."*

### Delivers

- **R1 — Resource registration + content-hash.** **Resolve and hash every profile-declared resource
  member** — the frequency dictionary and each period-dictionary — *through the language profile*
  (`cfg.language.frequency_dictionary`, `cfg.language.period_dictionaries`, `cfg.language.oracle_min`),
  computing a **content-derived version** so a swap/re-OCR is detectable. "Member" = the **declared
  resource unit** fixed by config (each `PeriodDictionary` entry + the frequency dict), never "whatever
  a downstream oracle eventually loads" — the set cannot drift with a future consumer. S3.0 does **not**
  construct the ≥N-of-M oracle (that is M6/BR-001; the oracle-*gating* is S3.1).
- **R2 — Normalization policy.** Make the *pre-lookup* fold normalization an explicit object **built
  from the profile**, with a deterministic **version**, so a normalizer change is detectable. S3.0's
  policy is the **oracle fold path** — `case_fold` + `accent_fold` only (see D-F). Tokenization and the
  boundary-search predicate are **not** S3.0's (D-B/D-F).
- **R3 — Lineage versioning, two distinct stale classes.** Both versions enter a lineage value object
  with **separate stale classes** so S8.1 can route *resource swap → re-segment* vs *normalizer change
  → re-derive offsets* as different repairs (§3.6).
- **R4 — Engine-agnostic.** All of the above sourced through the profile; the neutrality tier stays
  green; proven not-Italian-only by a second synthetic profile **built to break on any bake** (D-F,
  test 10).

### Explicitly NOT in S3.0 (owned by neighbours)

1. **The `structure_map.json` header schema** that *embeds* these versions → **S4.4** (tracker 450
   consumes "the resource + normalizer versions (S3.0)"). S3.0 produces the value object + its
   `to_json()` fragment; S4.4 assembles the manifest header.
2. **The stale-fail *loader* / migration router** that *compares* a stored version to the current one
   and routes the repair → **S8.1** (tracker 512). S3.0 *produces and registers* the versions +
   classes; S8.1 *consumes* them. (Same split S1.5 took: it registered `ATOM_STORE_STALE_CLASS`; S8.1
   routes on it.) So **no `from_json` / stale-compare in S3.0.**
3. **Zipf-DP word-segmentation + oracle-gating + the boundary-search predicate** → **S3.1** (dep on
   S3.0). The **tokenizer** identity (`spacy_model`) and the **search** predicate (`word_letter_class`)
   are versioned by S3.1's segmentation/search policy, not here. The **single canonical membership key**
   (full-token fold) is also S3.1's — built alongside its Zipf-DP consumer (D-F). S3.0 defines + versions
   the fold policy and proves its `chunk_key`/`probe_forms` ops reproduce the oracle fold path; S3.1
   wires them into segmentation.
4. **Rewiring `adjudicate`/`cleanup` consumers** through the shared policy. Out of "load + version"
   scope, and it touches the cleanup detcore-golden surface. First production consumer is S3.1; until
   then the fold ops are bound to reality by tests (§4), not left abstract (S3.1 integration hook,
   logged not silently dropped).

The seam in one line: **S3.0 = fold; S3.1 = tokenize + search.**

---

## 2. Surfaces it binds into (verified this session)

- `config/models.py` `LanguageProfile` already carries `frequency_dictionary` (str),
  `period_dictionaries: tuple[PeriodDictionary,…]`, `oracle_min: int`, `accent_fold: {"from","to"}`,
  `spacy_model`, `word_letter_class`. **No** `case_fold` field exists — the one field S3.0 adds (D-B).
- `paths.py` `asset_path` / `require_asset(rel, kind=…)` — resolution chokepoint; `MissingInputError`
  (exit 3) for a missing/typo'd asset. `ASSETS_ROOT = engine/assets` (dev symlinks).
- `structure/artifacts.py` — established home for per-layer schema-version + stale-class constants
  (`ATOM_STORE_SCHEMA_VERSION=1`, `ATOM_STORE_STALE_CLASS="atom-stream"`, `STRUCTURE_MAP_SCHEMA_VERSION`,
  `RELATION_STORE_SCHEMA_VERSION` — note: **no** stale-class constants for the latter two yet; do not
  mint them here, D-D). Neutral by construction.
- `structure/roundtrip.py` `hash_raw(text) -> "sha256:<hex>"` — the substrate **text** hash (UTF-8
  encode of a `str`). **Not reused for resource files** (D-C): a new `_sha256_bytes(data: bytes)` hashes
  raw bytes, and the canonical-JSON descriptor path encodes its string to UTF-8 bytes through the *same*
  `_sha256_bytes` — one digest producer, `sha256:` prefix kept.
- `util/jsonio.py` `atomic_write_json` (`indent=2, ensure_ascii=False, allow_nan=False`).
- `dictionaries/frequency.py` `load_word_set(path)`, `dictionaries/symspell.py` `load_symspell(path)`
  — existing **path-keyed** cached loaders (they cache a *loaded index for use*; S3.0's digest path does
  **not** copy this caching, D-C). `membership_oracle.py` / `period_dict.py` are M6 stubs.
- `steps/adjudicate.py` `DictionaryOracle` — the live fold path S3.0's policy reproduces: `chunk_key`
  = `word[0].lower().translate(fold)` (adjudicate.py:114); probe forms `[word, word.translate(fold)]`
  — the folded form only when it differs from `word` (:116–122); `word_letter_class` used only by
  `_search_chunk`'s boundary regex (:68–70) — the
  *search*, not the fold.
- Dictionary `index.json` (verified): top-level `chunks` is a **chunk-keyed dict** (letter keys, plus
  Hoare's `_INDEX`), each value `{file, lines, …}`. Zingarelli/Edgren expose Italian letters; Hoare adds
  `_INDEX → en_index.txt`. Every other file in a member dir is **undeclared** and therefore not hashed:
  `index.json` itself, `00_front_matter.txt` (Zingarelli), `headwords.json` (Edgren/Hoare — and not even
  `.txt`), and `raw.txt` (the regenerable download — present in Edgren/Hoare, **absent** in Zingarelli;
  tracked-vs-ignored status is parent-repo-governed and varies). That present-or-absent variance is
  exactly why a glob would be unstable and `chunks[*].file` is the rule — the digest is independent of
  any file's git status. So `chunks[*].file` is the **declared** set the digest versions. (Caveat, F1
  audit: the *current* `DictionaryOracle` loads `{word[0]}.txt` directly and never reads `index.json`,
  and Hoare's `_INDEX → en_index.txt` back-index is declared+hashed but not loaded by that `{letter}.txt`
  path — so the declared set is the versioned set *by construction*, not provably identical to the
  live-consumed set. Reconciling the two is M6/S3.1's, when the oracle's `index.json`-reading contract
  is fixed; until then the digest versions the declared set, and F1's chunk-key-in-identity keeps it
  sensitive to a routing-key remap.)
- Neutrality guards: `test_structure_neutrality` scans `src/engine/structure/**` (covers
  `structure/lineage.py`); `test_core_neutrality` scans all `src/engine/**` for book/typeface terms
  only — **neither** language-scans `dictionaries/normalization.py` (D-F / test 11).

---

## 3. Design

### D-A — Module split

- **`dictionaries/normalization.py`** — the *behaviour*: `NormalizationPolicy` built from the profile,
  exposing the fold ops `chunk_key(token)`, `probe_forms(token)` (D-F) and `descriptor() -> dict`.
  Beside `frequency.py`/`symspell.py`.
- **`structure/lineage.py`** — the *versioning*: `_sha256_bytes`, the canonical-JSON helper, and the
  `ResourceLineage` value object (D-E). Neutral — reads paths/tables from the profile, carries no
  language literal.
- **`structure/artifacts.py`** — add the stale-class + schema-version constants (D-D), beside the three
  existing.

Rationale: mirrors loaders (`frequency`/`symspell`) being separate from substrate versioning
(`atom_store`/`artifacts`); `structure/` carries only hashes + class strings, so the neutrality scan
has nothing to catch.

### D-B — Normalization-policy config shape (the one schema change)

- **`case_fold`** — **ADD `case_fold: str`** to `LanguageProfile` + `language_profile.schema.json` +
  the Italian profile (`"lower"`). Enum `{"lower","casefold","none"}`. This is the axis currently baked
  as a literal `.lower()` — the "core literal" the task says to source from the profile; a non-Latin
  book needs `"none"`/`"casefold"`, so it must be config.
- **`accent_fold`** — **reuse** the existing `{"from","to"}` field. Do **not** add a second copy
  (M4b-D1: duplicating the fold table reintroduces the multi-site-divergence bug it was consolidated to
  kill).
- **tokenizer** — **not in S3.0.** `spacy_model` and `word_letter_class` move to S3.1's
  segmentation/search policy version (they are not applied by any S3.0 fold op — D-F).

Net schema delta: **one new required field, `case_fold`.**

**Extensibility.** Future `*_fold` axes are absorbed by *indirection*, not pre-nested JSON.
`NormalizationPolicy.descriptor()` is a named-axis map; the normalizer version hashes the whole
descriptor, so a new axis (e.g. `width_fold` for CJK, `digit_fold`) costs one profile field + one
schema entry + one `descriptor()` line, and automatically becomes a version input — version/lineage/
stale machinery untouched. New folds stay flat siblings of `accent_fold`. Revisit JSON nesting only
when a *second* new fold axis arrives (defer-until-real-second-case, as BR-007 / the override
deep-merge).

### D-C — Resource hashing (content-derived bytes; index.json file set; no cache; fail-loud)

- **Bytes, not text, not mtime.** `_sha256_bytes(path.read_bytes())` per file. `mtime`
  false-positives on a no-op `touch`/re-checkout and false-negatives on a content-preserving copy;
  `read_text` would hide a CRLF/encoding change behind universal-newline translation.
- **Frequency dict** → `_sha256_bytes` of the file.
- **Each period member** → digest over the files declared by its `index.json` `chunks[*].file`,
  **sorted by chunk key** for determinism, hashing the ordered list of `(chunk-key,
  declared-file-identity, content_hash)` triples. The **chunk key** is part of the identity, not only
  the sort order (F1, #27 audit): it versions the declared *key→file binding* (re-declaring the same
  file+bytes under a different key moves the version — a filename-only digest would miss it). The
  *current* `DictionaryOracle` routes by filename (`word[0]`→`{letter}.txt`) and never reads this key,
  so this is conservative forward-coverage for a future `index.json`-reading oracle (see the §2
  consumed-set caveat), not a change the present system routes on. So adding/removing a declared chunk
  trips the version (identity in), a routing-key remap
  trips it (key in), a chunk's content change trips it (content in), and `index.json`'s own incidental
  metadata (counts/sizes) does **not** (manifest bytes out). This excludes every undeclared file —
  `raw.txt`, `00_front_matter.txt`, the derived JSON — regardless of its git status; only the declared
  set is hashed.
- **Fail-loud, never silent-skip.** A file declared in `chunks` but **absent on disk** →
  `MissingInputError` (a truncated dictionary must not hash as complete). A member dir with **no
  `index.json`** → `MissingInputError` (never a glob fallback — the bare glob is exactly the instability
  this rule removes; a future legacy member opts in with an *explicit file filter*). A present-but-
  *undeclared* stray file is correctly ignored (it is not in `chunks`).
- **`oracle_min`** folds into the resource descriptor (2-of-3 → 3-of-3 is a semantic resource change).
- **No digest cache.** Hashing the resource set is a once-per-`build()` op (~tens of MB, milliseconds);
  a path-keyed cache on the digest whose job is to detect content change is self-defeating, so it is
  removed outright (not fingerprint-keyed — that is the right design only if a perf problem appears).

*Why content-hash, not a name/version label:* a period dictionary's text is frozen, so the hash guards
the axes that move — member swap/add/remove (Hoare 1915 was added as the third member; a sibling book
can swap via a manifest `override`), **re-OCR** of the same source (same name, different bytes — a
label silently passes it while the oracle's answers shift), `oracle_min` change, and the regenerable
frequency dict. Only a content hash catches a re-OCR. No frozen-vs-mutable config distinction (it would
add a config axis, save milliseconds, and miss re-OCR).

**Atomic levels.** The lineage fragment carries two tiers (mirroring the atom store's whole-anchor +
per-atom duality): a **rolled-up `resource_version`** (the stale-trip wire S8.1 keys on) and the
**per-member** hashes that produced it. Granularity = the **swap unit** (a book swaps a whole
dictionary, not a letter-chunk); per-chunk is computed internally to fold each member's digest but is
**not** surfaced. This gives S8.1's *why-stale → which-migration* the localization to name "Zingarelli
1922 changed".

### D-D — Two distinct stale classes (in `structure/artifacts.py`)

`RESOURCE_STALE_CLASS = "resource-set"`, `NORMALIZER_STALE_CLASS = "normalization-policy"`, plus
`RESOURCE_LINEAGE_SCHEMA_VERSION = 1`. The distinctness test asserts these differ from each other **and
from `ATOM_STORE_STALE_CLASS`** — the classes that exist *after this task*. It does **not** reference
structure-map / relation-store stale classes (no such constants exist; minting them here is scope creep
into S4.4/S7.1c, which own them).

### D-E — Lineage value object (`structure/lineage.py`)

Frozen dataclass. Each descriptor is held **internally as its canonical JSON string** — immutable, and
by construction the exact bytes `_sha256_bytes` hashed, so the *stored* descriptor cannot drift from its
version. (The `to_json()` lineage fragment instead emits the *parsed* descriptor for readability — it
does **not** carry the literal hashed string; the binding is re-established by re-canonicalizing, test 7.)

```
ResourceLineage(
    resource_version: str,            # "sha256:…" rolled-up over the resource descriptor
    resource_descriptor: str,         # canonical JSON: {oracle_min, frequency, members:[{name,kind,dir,hash}, …]}
    resource_stale_class: str,        # RESOURCE_STALE_CLASS
    normalizer_version: str,          # "sha256:…" over the normalizer descriptor
    normalizer_descriptor: str,       # canonical JSON: {case_fold, accent_fold}  (D-F)
    normalizer_stale_class: str,      # NORMALIZER_STALE_CLASS
    schema_version: int,              # RESOURCE_LINEAGE_SCHEMA_VERSION
)
```

- `build(cfg) -> ResourceLineage` loads + hashes via the profile. **No `from_json` / stale-compare**
  (S8.1).
- `to_json()` emits the parsed descriptors (as dicts, for readability) — the header fragment S4.4
  embeds. The hashed canonical strings are the private stored form; the binding test recomputes from
  the emitted dicts through the *same* canonicalizer (D-G / test 7).
- **Journal-readiness.** S3.0 builds a *diffable record*, not a history log (history = S8.1). Three
  properties make it journalable: `schema_version` (schema evolution), canonical serialization (byte-
  diffable), and per-member + per-axis descriptors (a diff is *localizable* — "Zingarelli changed",
  "case_fold lower→casefold" — not just "something moved"). The `oracle_min`, the frequency-dict
  content hash (carried as a sibling `frequency` key — a flat file has no `{name,kind,dir}` member
  shape to fit, so it rides the descriptor beside `members` rather than overloading those fields), and
  per-member `dir`/`hash` are surfaced in `resource_descriptor` so every input to `resource_version`
  is visible to a diff. Note (F2, #27 audit, kept-by-decision): a member's `name`/`kind`/`dir` are
  hashed *into* `resource_version`, not merely surfaced — so resource-version tracks the member's
  **declaration identity**, not only its oracle-observable content, and a cosmetic rename re-segments.
  That is a deliberate false-positive on the over-migration side (re-derive needlessly, never miss a
  real change), accepted not fixed; contrast the normalizer tier (invariant 17 — versions exactly the
  applied axes) and the frequency hash (content-only).

### D-F — The normalization policy = the oracle fold path

There is no single "the normalization" in the live code: `load_word_set` lowercases only (accents
preserved); `normalize_for_comparison` is `lower → NFKD-strip → drop [^a-z]`; `DictionaryOracle` folds
the first char for chunk selection and probes two forms via the `accent_fold` **table** (not NFKD).
S3.0 owns **only** the oracle/segmentation fold path (the membership path S3.1 oracle-gates on) — not
`normalize_for_comparison` (heading/ordinal matching) nor `load_word_set`'s bare-lower; unifying all
three is the consumer refactor Q4 defers.

Operations exposed (all reading **only** `{case_fold, accent_fold}`), each with a **live
`DictionaryOracle` referent** to bind against (test 8):

- **`chunk_key(token)`** — first-char case+accent fold → which chunk to load (oracle's
  `word[0].lower().translate(fold)`).
- **`probe_forms(token)`** — the ordered `[original, accent-folded]` forms the legacy oracle
  boundary-searches (oracle's `[word, word.translate(fold)]`, the folded form appended only when it
  differs from the original — an unaccented token yields a single form).

A *single canonical membership key* (full token, case+accent folded — the form S3.1's Zipf-DP would
consult) is **deferred to S3.1**, not exposed here: it has **no S3.0 consumer** and **no live oracle op
to bind a test against** (the oracle searches `probe_forms`; it never computes one full-token key), so
building it now would force a weak own-literal test for an unused op. S3.1 defines it alongside its
consumer. This keeps every S3.0 op grounded in a real oracle behaviour.

`word_letter_class` is **absent** from `normalizer_descriptor` (it is consumed only by the boundary
*search*, → S3.1), so `normalizer_descriptor = {case_fold, accent_fold}` **unconditionally**. A test
asserts **descriptor-keys == the ops' actual profile inputs** — a hollow input (hashed-but-unused) or a
silent omission (used-but-unhashed) turns the suite red, operationalizing "version only what you apply"
rather than trusting the naming. (The class stays `NormalizationPolicy` — it *is* a policy over these
ops; the rejected `normalize()` method name over-claimed universality.)

### D-G — Determinism

Descriptors are canonicalized via `json.dumps(…, sort_keys=True, ensure_ascii=False,
separators=(",",":"))` and hashed through `_sha256_bytes` (the canonical string encoded to UTF-8). A
single `_canonical(obj) -> str` helper produces both the stored string and the hashed bytes.
`build(cfg)` twice yields byte-identical versions; the resource descriptor's member list is normalized
(members **sorted by `name`**, each unique) and each member's files are sorted by chunk key (D-C), so a
reorder of `period_dictionaries` in the profile JSON does not change `resource_version`. The recompute-from-parsed-dict binding
(test 7) is valid only if `_canonical` is **stable under a JSON round-trip**
(`_canonical(json.loads(_canonical(d))) == _canonical(d)`) — asserted, not assumed (test 16).

---

## 4. Red-first test matrix

Per `feedback_red_first_tests`: each invariant is written to fail first on its violation, named by the
red input. Home: `tests/unit/test_resource_lineage.py` (+ the normalization-neutrality assertions).

1. **Resource version ↔ content, same path.** Rewrite *different bytes at the same resolved path* ⇒
   `resource_version` changes; rewrite *identical bytes* / `touch` ⇒ unchanged. *Kills* path-only,
   mtime-based, and a stale cache. (A different-paths test would not — it passes for a path-only hash.)
2. **Resource-version independent of the normalizer.** Change only `case_fold`/`accent_fold` ⇒
   `resource_version` unchanged.
3. **Normalizer version moves on a policy change.** `case_fold` lower→casefold, or `accent_fold` ⇒
   `normalizer_version` differs.
4. **Normalizer-version independent of resources.** Swap a dict ⇒ `normalizer_version` unchanged.
   (3+4 are the "two distinct stale classes" property in behaviour.)
5. **Distinct stale classes, no collision.** `RESOURCE_STALE_CLASS != NORMALIZER_STALE_CLASS`, both
   differ from `ATOM_STORE_STALE_CLASS` (existing classes only — not structure-map/relation).
6. **Determinism.** `build(cfg)` twice ⇒ identical `ResourceLineage`; reordering `period_dictionaries`
   in the profile ⇒ `resource_version` unchanged.
7. **Versions correspond to descriptors (binding, not shape).** Recompute `resource_version` and
   `normalizer_version` from the descriptors emitted by `to_json()` (through the same `_canonical`) ⇒
   exact equality. (Not "non-empty exists".)
8. **Fold ops reproduce the oracle fold path.** `chunk_key` and `probe_forms` match `DictionaryOracle`'s
   fold behaviour on representative tokens (incl. an accented one) — bound to the *live oracle ops
   specifically* (`word[0].lower().translate(fold)` and `[word, word.translate(fold)]` — folded form
   only when it differs), not a vague
   "live behaviour". No `lookup_key` here — it is deferred to S3.1 (D-F), having no live oracle referent.
9. **Loads via the profile; bindings resolve (hard, no skip).** `build(load_book("per_la_liberta"))`
   succeeds; the frequency dict + every period-dictionary dir resolve via `require_asset`
   (`feedback_validate_bindings`); a missing/typo'd asset raises `MissingInputError`.
10. **Sourced-not-baked / not-Italian-only.** A **second synthetic** profile built to *break on any
    bake* — a **non-Latin-script** token (catches `[a-z]`/ASCII), `case_fold:"none"` or a
    **case-sensitive** profile (catches a hardcoded `.lower()`), and an **accent-fold table unlike
    Italian's** (catches a baked `_ACCENT_MAP`) — yields a correspondingly different `normalizer_version`
    and fold output, exercising every branch behaviourally.
11. **Neutrality green.** `structure/lineage.py` trips no `test_structure_neutrality` term. For
    `dictionaries/normalization.py` (unguarded by both existing scans), the **behavioural** guard is
    test 10 (the real guard); a targeted source-language literal scan is added belt-and-suspenders only
    (a naive `.lower()`/`a-z` scan false-positives on neutral code).
12. **Mutation proof.** Hand-mutate the hashing + the descriptor assembly (drop a descriptor field,
    weaken the fold, collapse the two stale classes) ⇒ the suite kills each (0 survivors).
13. **Per-member tier localizes a change.** Changing one period member's bytes moves that member's hash
    **and** the rolled-up `resource_version`, other members' hashes unchanged; the roll-up is a pure
    function of the member hashes. *Red:* a roll-up-only version → unlocalizable → fail.
14. **Lineage record is journal-diffable.** Two `to_json()` records differing only in `case_fold` differ
    *only* in `normalizer_version` + `normalizer_descriptor` (resource tier byte-identical), and
    vice-versa for a dict swap.
15. **Fail-loud on a broken file set.** A `chunks`-declared file absent on disk ⇒ `MissingInputError`;
    a member dir with no `index.json` ⇒ `MissingInputError`. *And* the converse: a present-but-
    *undeclared* stray file in a member dir ⇒ `resource_version` unchanged.
16. **Canonicalizer round-trip stability.** `_canonical(json.loads(_canonical(d))) == _canonical(d)`
    for the descriptor value types (strings, the `oracle_min` int, nested string maps) — the
    precondition test 7's recompute rests on.
17. **Descriptor-keys == ops' inputs (no hollow version).** `normalizer_descriptor`'s keys equal
    exactly the profile fields the fold ops read (`{case_fold, accent_fold}`); a field hashed-but-unused
    or used-but-unhashed turns the suite red. (Operationalizes D-F.)
18. **Stale-class wire values pinned (persisted contract).** The literal strings `to_json()` emits for
    `resource_stale_class` / `normalizer_stale_class` equal exactly `"resource-set"` /
    `"normalization-policy"` — pinned at the **serialization site** (the emitted record), *not* against
    the bare constants (which would only restate their own literal). Mirrors the atom-store envelope pin
    (`test_atom_store.py`: `env["stale_class"] == "atom-stream"`). *Red:* rename either discriminator and
    the persisted value drifts while distinctness (5) / diffability (14) / version-binding (7) all stay
    green — this is the invariant that catches it. S4.4 writes these into `structure_map.json` and S8.1
    routes on them, so the literal is a wire contract, not an internal name. (From the #23 pre-commit
    audit, F1; written red in #25 against the stub `to_json`, greened at #27.)

### Done-when → proof map

| Done-when clause | Proven by |
|---|---|
| resources load via the profile | 9 (binding, hard) + 1 + 15 |
| normalizer loads via the profile | 8, 10, 17 |
| both hashes enter lineage | 7 (binding) + 14 |
| two distinct stale classes | 2, 4, 5, 18 (wire-value pin) |
| neutrality tier green | 10 (behavioural) + 11 |

---

## 5. Build order (red-first)

1. `structure/artifacts.py` constants (D-D) + the failing distinctness test (5).
2. **Config `case_fold`** — `models.py` + `language_profile.schema.json` + the Italian profile +
   `loader.py`, **plus the ripple**: it is a required field (matching the profile's all-required style),
   so every direct `LanguageProfile` constructor / fixture gains it. Prerequisite — the policy and the
   synthetic test profiles (3, 10) read it, so it lands before the red battery can even be *written*.
3. **Minimal importable stubs** — `_sha256_bytes`, `NormalizationPolicy` (`chunk_key`/`probe_forms`/
   `descriptor`), `ResourceLineage` (`build`/`to_json`) as real signatures raising `NotImplementedError`.
   So the red battery *collects and runs* and each test fails **on its own assertion**, not on an
   `ImportError` at collection (a collection error is one uninformative red, not invariant-by-invariant
   — the same skeleton-first pattern `artifacts.py` / the M6 stubs already use).
4. `tests/unit/test_resource_lineage.py` — the full red battery (1–18) against those stubs.
5. `_sha256_bytes` + the `_canonical` helper (green 6, 16; the binding half of 7).
6. `dictionaries/normalization.py` `NormalizationPolicy` — `chunk_key`/`probe_forms`/`descriptor`
   (green 8, 17; **advances** 3, 4, 10 — they complete at #27 once `build`/`_sha256_bytes`/`_canonical`
   land: 3/4 route through `ResourceLineage.build` (step 8), 10's fold-op assertions green here but its
   `_normalizer_version` tail needs `_canonical`/`_sha256_bytes` (step 5). The GitHub #26/#27 split folds
   plan step 5 into #27, so neither exists at #26.).
7. Resource digest over `index.json` `chunks[*].file` + fail-loud (green 1, 13, 15).
8. `structure/lineage.py` `ResourceLineage.build`/`to_json` (green 2, 7, 9, 14, 18).
9. Neutrality + mutation pass (11, 12); full suite + ruff green.

---

## 6. Provenance

Consolidated 2026-06-29 from `s3_0_plan_discussion.md` — the inline audit (12 findings) plus three
follow-up rounds. Net changes from the first draft, all settled in that doc: resource hash is `bytes`
not `hash_raw`-of-text; the period-member file set is `index.json` `chunks[*].file` (fail-loud on
absent/no-index), not a glob; no digest cache; the tokenizer (`spacy_model`) and search predicate
(`word_letter_class`) move to S3.1, leaving `normalizer_descriptor = {case_fold, accent_fold}`; the
policy exposes `chunk_key`/`probe_forms` (not `normalize()`; the canonical membership key `lookup_key`
is deferred to S3.1, having no live oracle referent); descriptors are stored as canonical JSON strings
(`to_json()` emits parsed dicts; the binding is re-established by re-canonicalizing, not by carrying the
hashed bytes); `resource_descriptor` is surfaced for localizable diffs; the stale-class
distinctness test references existing classes only; and the test battery gained the same-path content
test, the recompute-binding test, the strengthened not-Italian-only fixture, and the fail-loud,
canonicalizer-idempotence, and descriptor-keys==ops-inputs invariants.

A follow-up **#23 pre-commit audit** (2026-06-29) added invariant 18 — the stale-class wire-value pin
— on the atom-store precedent (`test_atom_store.py:169`), closing the gap that a discriminator rename
would pass 5/7/14 green while silently changing the value S4.4 persists and S8.1 routes on.
