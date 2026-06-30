"""S3.0 resource + normalization-policy lineage — the red-first invariant battery.

Home of the S3.0 lineage battery (ENGINE_STRUCTURE_PLAN S3.0; ``docs/s3_0_plan.md`` §4), built
red-first across the S3.0 build order (§5). #23 seated the stale-class distinctness invariant
(test 5) against the constants in ``structure/artifacts.py``. #25 adds invariants **1–4, 6–10, and
13–18** against the importable stubs (``structure/lineage.py``, ``dictionaries/normalization.py``):
each currently fails on the stub's ``NotImplementedError`` and greens surface-by-surface as #26
(fold ops) and #27 (resource digest + lineage) land. This commit is red by design — the battery is
the red-first evidence, not a regression. It also pins two resource-digest design properties D-C
states but §4 never numbered — ``oracle_min`` as a resource-version input, and index.json
manifest-bytes-out — surfaced by the #25 adversarial audit as "passes even if the impl drops them".

Two invariants are **not** here: 11 (a targeted source-language scan over ``normalization.py``,
unguarded by the existing neutrality tiers) and 12 (the hand-mutation pass) are green-*down*
validation, not fail-against-stub assertions, so they land with the neutrality + mutation pass in
#28 (§5.9). The structure-half of 11 needs no new test — ``test_structure_neutrality`` already globs
``structure/lineage.py``.

The ``to_json()`` shape the battery pins (the contract #27 implements, the fragment S4.4 embeds)::

    {
      "schema_version": <int>,
      "resource":   {"version": "sha256:…", "stale_class": "resource-set",
                     "descriptor": {"oracle_min": <int>,
                                    "members": [{"name","kind","dir","hash"}, …]}},
      "normalizer": {"version": "sha256:…", "stale_class": "normalization-policy",
                     "descriptor": {"case_fold": <str>, "accent_fold": {"from","to"}}},
    }

where ``<tier>["version"] == _sha256_bytes(_canonical(<tier>["descriptor"]).encode("utf-8"))`` — the
binding invariant 7 recomputes, valid because ``_canonical`` is round-trip stable (invariant 16).

Invariant 5 — two distinct stale classes (D-D). ``RESOURCE_STALE_CLASS`` and
``NORMALIZER_STALE_CLASS`` must differ from each other and from the one persisted-layer class that
exists after this task (``ATOM_STORE_STALE_CLASS``), so governance (S8.1) routes a *resource swap →
re-segment* and a *normalizer change → re-derive offsets* as **different** repairs (§3.6). Red-proof:
collapse the two classes to one literal, or alias either onto ``ATOM_STORE_STALE_CLASS``, and the
set-size assertion goes red.

A second check here — ``test_resource_lineage_schema_version_is_a_positive_int`` — is a binding
sanity check on ``RESOURCE_LINEAGE_SCHEMA_VERSION`` (feedback_validate_bindings), **not** a §4
numbered invariant. #25 must not re-seat either (both already live here).
"""

from __future__ import annotations

import dataclasses
import json

import pytest

import engine.structure as structure
from engine import paths
from engine.config.loader import load_book
from engine.dictionaries.normalization import NormalizationPolicy
from engine.errors import MissingInputError
from engine.structure.lineage import ResourceLineage, _canonical, _sha256_bytes
from engine.util.text import build_fold_table

REAL_BOOK = "per_la_liberta"


# --- fake-asset staging (mutable resource tree mirroring the real declared paths) ---------- #

def _member_layout() -> dict:
    """member dir (assets-relative) → {chunk_key: (filename, content_bytes)}.

    Mirrors the real config's three declared period-dictionary dirs, each with distinct bytes so a
    test can prove one member's hash moves independently of the others (invariant 13).
    """
    return {
        "dictionary/zingarelli_1922": {"A": ("a.txt", b"abaco\nabate\n")},
        "dictionary/edgren_1901": {"A": ("a.txt", b"alfa\nalbero\n")},
        "dictionary/hoare_1915": {"A": ("a.txt", b"acca\nacqua\n")},
    }


def _stage_assets(root, *, freq: bytes = b"alpha 5\nbeta 3\n", layout: dict | None = None) -> None:
    """Write a small, mutable asset tree: the frequency file + each period member (index.json +
    its declared chunk files), at exactly the assets-relative paths the real profile names."""
    (root / "frequency").mkdir(parents=True, exist_ok=True)
    (root / "frequency" / "it_combined.txt").write_bytes(freq)
    for rel, chunks in (layout or _member_layout()).items():
        member = root / rel
        member.mkdir(parents=True, exist_ok=True)
        # incidental metadata (counts/sizes) mirrors the real index.json shape; the resource digest
        # hashes only chunks[*].file identity + chunk content (D-C "manifest bytes out"), so a test
        # can churn these and prove the version is stable.
        index = {
            "chunks": {
                key: {"file": filename, "lines": 10, "size_kb": 1.5}
                for key, (filename, _) in chunks.items()
            }
        }
        (member / "index.json").write_text(json.dumps(index), encoding="utf-8")
        for _key, (filename, content) in chunks.items():
            (member / filename).write_bytes(content)


@pytest.fixture
def fake_assets(tmp_path, monkeypatch):
    """A mutable asset tree mirroring the real declared paths, with ``ASSETS_ROOT`` pointed at it.

    Returns ``(cfg, root)``: ``cfg`` is the real PLL config (whose frequency/dictionary rel-paths now
    resolve under the patched root); ``root`` is the tmp tree a test mutates before rebuilding. The
    config loads from the real profiles (unaffected by ``ASSETS_ROOT``); only ``build``'s
    ``require_asset`` resolution is redirected.
    """
    root = tmp_path / "assets"
    _stage_assets(root)
    monkeypatch.setattr(paths, "ASSETS_ROOT", root)
    return load_book(REAL_BOOK), root


def _with_language(cfg, **changes):
    """A copy of ``cfg`` with ``cfg.language`` fields replaced (frozen-dataclass ``replace``)."""
    return dataclasses.replace(cfg, language=dataclasses.replace(cfg.language, **changes))


def _normalizer_version(policy: NormalizationPolicy) -> str:
    """The normalizer version a policy alone implies — the same formula ``build`` uses."""
    return _sha256_bytes(_canonical(policy.descriptor()).encode("utf-8"))


# --- invariant 5 + schema-version sanity (seated in #23 — do not re-seat) ------------------ #

def test_resource_and_normalizer_stale_classes_are_distinct():
    # D-D / invariant 5. The two S3.0 stale classes and the existing atom-store class are three
    # different routing keys; any collision would have S8.1 apply the wrong migration.
    resource = structure.RESOURCE_STALE_CLASS
    normalizer = structure.NORMALIZER_STALE_CLASS
    atom = structure.ATOM_STORE_STALE_CLASS
    # a stale class is a wire discriminator — never blank
    assert isinstance(resource, str) and resource
    assert isinstance(normalizer, str) and normalizer
    # distinct from each other and from the only persisted-layer class minted so far (S4.4/S7.1c
    # have not minted theirs — asserting against non-existent constants would be scope creep)
    assert len({resource, normalizer, atom}) == 3


def test_resource_lineage_schema_version_is_a_positive_int():
    # The lineage record (S4.4 embeds it) carries its own schema version, independent of the three
    # persisted-layer versions, so its shape can evolve without bumping a layer. bool is excluded
    # (int subclass) so a stray True/False cannot masquerade as a version.
    version = structure.RESOURCE_LINEAGE_SCHEMA_VERSION
    assert isinstance(version, int) and not isinstance(version, bool)
    assert version >= 1


# --- invariant 1 — resource version ↔ content, same path ----------------------------------- #

def test_resource_version_tracks_content_at_the_same_path(fake_assets):
    cfg, root = fake_assets
    freq = root / "frequency" / "it_combined.txt"
    v0 = ResourceLineage.build(cfg).resource_version
    # rewrite identical bytes (a touch / re-checkout) ⇒ unchanged: kills mtime-based + a stale cache
    freq.write_bytes(freq.read_bytes())
    assert ResourceLineage.build(cfg).resource_version == v0
    # different bytes at the SAME resolved path ⇒ changed: kills a path-only "version"
    freq.write_bytes(b"totally different content\n")
    assert ResourceLineage.build(cfg).resource_version != v0


# --- invariant 2 — resource version independent of the normalizer -------------------------- #

def test_resource_version_is_independent_of_the_normalizer(fake_assets):
    cfg, _ = fake_assets
    lower = ResourceLineage.build(_with_language(cfg, case_fold="lower"))
    none_fold = ResourceLineage.build(_with_language(cfg, case_fold="none"))
    # only the fold policy changed; the resource bytes are identical ⇒ resource_version unmoved
    assert lower.resource_version == none_fold.resource_version


# --- invariant 3 — normalizer version moves on a policy change ----------------------------- #

def test_normalizer_version_moves_on_a_policy_change(fake_assets):
    cfg, _ = fake_assets
    base = ResourceLineage.build(cfg).normalizer_version
    # the case axis…
    assert ResourceLineage.build(_with_language(cfg, case_fold="none")).normalizer_version != base
    # …and the accent axis each move the normalizer version
    other_fold = {"from": "ÆØ", "to": "AO"}
    assert ResourceLineage.build(_with_language(cfg, accent_fold=other_fold)).normalizer_version != base


# --- invariant 4 — normalizer version independent of resources ----------------------------- #

def test_normalizer_version_is_independent_of_resources(fake_assets):
    cfg, _ = fake_assets
    full = ResourceLineage.build(cfg)
    # drop one period dictionary (a resource swap) — the staged tree still resolves the rest
    fewer = ResourceLineage.build(
        _with_language(cfg, period_dictionaries=cfg.language.period_dictionaries[:-1])
    )
    assert fewer.normalizer_version == full.normalizer_version  # fold untouched ⇒ unmoved
    assert fewer.resource_version != full.resource_version       # but it WAS a resource change


# --- invariant 6 — determinism + reorder-invariance ---------------------------------------- #

def test_build_is_deterministic_and_reorder_invariant(fake_assets):
    cfg, _ = fake_assets
    assert ResourceLineage.build(cfg) == ResourceLineage.build(cfg)  # byte-identical, twice
    reordered = _with_language(
        cfg, period_dictionaries=tuple(reversed(cfg.language.period_dictionaries))
    )
    assert (
        ResourceLineage.build(reordered).resource_version
        == ResourceLineage.build(cfg).resource_version
    )


# --- invariant 7 — versions correspond to descriptors (binding, not shape) ----------------- #

def test_versions_recompute_from_the_emitted_descriptors(fake_assets):
    cfg, _ = fake_assets
    rec = ResourceLineage.build(cfg).to_json()
    res = rec["resource"]
    assert _sha256_bytes(_canonical(res["descriptor"]).encode("utf-8")) == res["version"]
    norm = rec["normalizer"]
    assert _sha256_bytes(_canonical(norm["descriptor"]).encode("utf-8")) == norm["version"]


# --- invariant 8 — fold ops reproduce the DictionaryOracle fold path ----------------------- #

def test_fold_ops_reproduce_the_dictionary_oracle():
    # Bound to the live oracle ops *specifically* (steps/adjudicate.py:114 chunk key;
    # :116-121 probe forms), not a vague "live behaviour". case_fold == "lower" in the real profile.
    cfg = load_book(REAL_BOOK)
    fold = build_fold_table(cfg.language.accent_fold)
    policy = NormalizationPolicy(
        case_fold=cfg.language.case_fold, accent_fold=cfg.language.accent_fold
    )
    # "Àncora" exercises an accented FIRST char (chunk-key fold); "perché"/"città" exercise the
    # accent-folded probe form; "Italia" the de-duplicated single-form branch.
    for token in ("Italia", "perché", "città", "Àncora"):
        # chunk_key == word[0].lower().translate(fold)  (adjudicate.py:114)
        assert policy.chunk_key(token) == token[0].lower().translate(fold)
        # probe_forms == [word, word.translate(fold)], the second only when it differs (the oracle
        # searches `stripped` only `if stripped != word` — adjudicate.py:118-121)
        folded = token.translate(fold)
        expected = [token] if folded == token else [token, folded]
        assert policy.probe_forms(token) == expected


# --- invariant 9 — loads via the profile; bindings resolve (hard, no skip) ----------------- #

def test_build_resolves_real_assets_and_fails_loud_on_a_typo():
    # Real assets (no patch): the frequency dict + every period-dictionary dir resolve via
    # require_asset and hash — hard, no skip (feedback_validate_bindings).
    cfg = load_book(REAL_BOOK)
    lineage = ResourceLineage.build(cfg)
    assert lineage.resource_version.startswith("sha256:")
    # a typo'd frequency dict ⇒ MissingInputError (require_asset), not a bare FileNotFoundError
    with pytest.raises(MissingInputError):
        ResourceLineage.build(_with_language(cfg, frequency_dictionary="frequency/NOPE.txt"))
    # …and a typo'd period-dictionary dir
    bad = (dataclasses.replace(cfg.language.period_dictionaries[0], dir="dictionary/nope"),)
    bad += cfg.language.period_dictionaries[1:]
    with pytest.raises(MissingInputError):
        ResourceLineage.build(_with_language(cfg, period_dictionaries=bad))


# --- invariant 10 — sourced-not-baked / not-Italian-only ----------------------------------- #

def test_synthetic_profile_breaks_on_any_bake():
    # A profile unlike Italian on every axis a bake could hardcode: a non-Latin (Greek) token, a
    # case-sensitive fold (case_fold="none" — catches a hardcoded .lower()), and a non-Italian
    # accent-fold table (catches a baked _ACCENT_MAP).
    greek_fold = {"from": "άέήίόύώ", "to": "αεηιουω"}
    table = build_fold_table(greek_fold)
    policy = NormalizationPolicy(case_fold="none", accent_fold=greek_fold)
    # case_fold="none": the uppercase first char is NOT lowered (a baked .lower() folds Ό→ό→ο)
    assert policy.chunk_key("Όμικρον") == "Ό".translate(table)
    assert policy.chunk_key("Όμικρον") != "Όμικρον"[0].lower().translate(table)
    # the accent fold applies to the probe forms; a baked Italian table would not touch ί
    assert policy.probe_forms("ποίηση") == ["ποίηση", "ποίηση".translate(table)]
    # and the whole policy versions differently from Italian's (different descriptor ⇒ different hash)
    italian = NormalizationPolicy(
        case_fold="lower", accent_fold=load_book(REAL_BOOK).language.accent_fold
    )
    assert _normalizer_version(policy) != _normalizer_version(italian)


# --- fold-op robustness: an unsupported case_fold mode fails loud (not a numbered §4 invariant) #
# case_fold is enum-bound at the schema, but a policy constructed directly (as this battery does)
# can carry a drifted mode — e.g. a 4th mode added to the schema without a matching fold op. The op
# must reject it loudly, not mis-route the chunk key by leaving the case unfolded. Exercises the
# _fold_case failure branch #26 adds; red if that branch falls through to a bare None.translate.

def test_chunk_key_fails_loud_on_an_unsupported_case_fold_mode():
    policy = NormalizationPolicy(case_fold="titlecase", accent_fold={"from": "à", "to": "a"})
    with pytest.raises(ValueError):
        policy.chunk_key("Àncora")


# The "lower" path has a live oracle referent (test 8); these two pin the case-axis branches the real
# Italian profile never exercises (feedback_red_first_tests / single-fixture blind spots — a
# non-default config value is born untested). The module docstring motivates "casefold" for a
# non-Latin/case-sensitive book, and the chunk_key docstring states the case-before-accent order;
# without these, a `casefold→lower` swap and an order reversal both survive the suite green.

def test_chunk_key_casefold_mode_differs_from_lower():
    # ẞ (capital sharp s) casefolds to "ss" but lowercases to "ß" — so this pins that "casefold" is
    # str.casefold, not a hardcoded .lower(). Fold table chosen not to touch the result.
    policy = NormalizationPolicy(case_fold="casefold", accent_fold={"from": "à", "to": "a"})
    assert policy.chunk_key("ẞoo") == "ss"          # casefold; a `.lower()` bake yields "ß"
    assert policy.chunk_key("ẞoo") != "ẞoo"[0].lower()


def test_chunk_key_lower_mode_differs_from_casefold():
    # The symmetric pin: the "lower" path — the one the real profile uses and the live oracle bakes
    # (adjudicate.py:114 word[0].lower()) — must be str.lower, not str.casefold. Without this, a
    # `.lower()`→`.casefold()` swap in the lower branch survives green (it diverges only on ẞ-like
    # chars absent from the all-"lower" Italian fixture), mis-routing "ß" to a 2-char "ss" chunk.
    policy = NormalizationPolicy(case_fold="lower", accent_fold={"from": "à", "to": "a"})
    assert policy.chunk_key("ẞoo") == "ß"           # lower; a `.casefold()` bake yields "ss"
    assert policy.chunk_key("ẞoo") != "ẞoo"[0].casefold()


def test_chunk_key_applies_case_before_accent():
    # A lowercase-only fold table makes the order observable: case-first lowers À→à then folds à→a
    # ("a"); accent-first would translate À (absent from the table) unchanged then lower it ("à").
    # Every real profile's table is case-complete (À→A and à→a both present), so the order is a no-op
    # there and only a synthetic asymmetric table can pin the docstring's load-bearing claim.
    policy = NormalizationPolicy(case_fold="lower", accent_fold={"from": "à", "to": "a"})
    assert policy.chunk_key("Àncora") == "a"        # case→accent; reversed order yields "à"


# --- invariant 13 — per-member tier localizes a change ------------------------------------- #

def test_per_member_hash_localizes_a_change(fake_assets):
    cfg, root = fake_assets
    before = {
        m["name"]: m["hash"]
        for m in ResourceLineage.build(cfg).to_json()["resource"]["descriptor"]["members"]
    }
    v0 = ResourceLineage.build(cfg).resource_version
    # mutate exactly one member's declared chunk
    (root / "dictionary" / "zingarelli_1922" / "a.txt").write_bytes(b"mutated\n")
    res = ResourceLineage.build(cfg).to_json()["resource"]
    after = {m["name"]: m["hash"] for m in res["descriptor"]["members"]}
    assert after["Zingarelli 1922"] != before["Zingarelli 1922"]  # the changed member moved
    assert after["Edgren 1901"] == before["Edgren 1901"]          # the others did not
    assert after["Hoare 1915"] == before["Hoare 1915"]
    assert res["version"] != v0                                   # and the roll-up moved with it
    # each member carries the full localizable shape (D-E), not just name+hash — so a diff can name
    # "Zingarelli 1922 (dictionary/zingarelli_1922) changed", not merely "a hash moved"
    for member in res["descriptor"]["members"]:
        assert set(member) == {"name", "kind", "dir", "hash"}


# --- invariant 14 — lineage record is journal-diffable ------------------------------------- #

def test_lineage_record_is_journal_diffable(fake_assets):
    cfg, _ = fake_assets
    # differ only in case_fold ⇒ only the normalizer tier moves
    lower = ResourceLineage.build(_with_language(cfg, case_fold="lower")).to_json()
    none_fold = ResourceLineage.build(_with_language(cfg, case_fold="none")).to_json()
    assert lower["resource"] == none_fold["resource"]      # resource tier byte-identical
    assert lower["normalizer"] != none_fold["normalizer"]  # normalizer tier differs
    # differ only in the dictionary set ⇒ only the resource tier moves
    full = ResourceLineage.build(cfg).to_json()
    fewer = ResourceLineage.build(
        _with_language(cfg, period_dictionaries=cfg.language.period_dictionaries[:-1])
    ).to_json()
    assert full["normalizer"] == fewer["normalizer"]       # normalizer tier identical
    assert full["resource"] != fewer["resource"]           # resource tier differs


# --- invariant 15 — fail-loud on a broken file set; undeclared stray ignored --------------- #

def test_fail_loud_when_a_declared_chunk_file_is_absent(fake_assets):
    cfg, root = fake_assets
    (root / "dictionary" / "zingarelli_1922" / "a.txt").unlink()  # declared in index.json, now gone
    with pytest.raises(MissingInputError):
        ResourceLineage.build(cfg)


def test_fail_loud_when_a_member_has_no_index(fake_assets):
    cfg, root = fake_assets
    (root / "dictionary" / "edgren_1901" / "index.json").unlink()  # no manifest ⇒ no glob fallback
    with pytest.raises(MissingInputError):
        ResourceLineage.build(cfg)


def test_an_undeclared_stray_file_is_ignored(fake_assets):
    cfg, root = fake_assets
    v0 = ResourceLineage.build(cfg).resource_version
    # a present-but-undeclared file (e.g. the regenerable raw download) is not in chunks ⇒ unmoved
    (root / "dictionary" / "hoare_1915" / "raw.txt").write_bytes(b"regenerable download\n")
    assert ResourceLineage.build(cfg).resource_version == v0


# --- D-C resource-digest design properties (not promoted to a numbered §4 invariant) ------- #
# oracle_min and index.json's incidental metadata are resource-digest guarantees the plan states
# (D-C) but §4 never numbered. Without a red-first pin, an #27 impl that drops oracle_min from the
# descriptor, or folds whole-index.json bytes into the digest, passes the entire battery — the
# "passes even if wrong" hole the #25 adversarial audit surfaced (A + B converged on oracle_min).

def test_resource_version_tracks_oracle_min(fake_assets):
    cfg, _ = fake_assets
    base = ResourceLineage.build(cfg)
    bumped = ResourceLineage.build(_with_language(cfg, oracle_min=cfg.language.oracle_min + 1))
    # 2-of-3 → 3-of-3 changes the membership verdict (a semantic resource change, D-C) and is the
    # ONLY resource input not already caught by the per-member byte hashes — so it needs its own pin.
    assert bumped.resource_version != base.resource_version       # resource tier moves
    assert bumped.normalizer_version == base.normalizer_version   # and it is not a normalizer change


def test_index_metadata_churn_does_not_move_the_version(fake_assets):
    cfg, root = fake_assets
    v0 = ResourceLineage.build(cfg).resource_version
    index = root / "dictionary" / "zingarelli_1922" / "index.json"
    data = json.loads(index.read_text(encoding="utf-8"))
    # same declared file set + same chunk bytes; only incidental counts/sizes churn (an index regen)
    data["chunks"]["A"]["lines"] = 99999
    data["chunks"]["A"]["size_kb"] = 4242.0
    data["_regenerated_note"] = "counts recomputed"
    index.write_text(json.dumps(data), encoding="utf-8")
    # D-C "manifest bytes out": the digest hashes chunks[*].file identity + content, not the index
    # bytes — so a no-op index regeneration must not trip a false re-segment.
    assert ResourceLineage.build(cfg).resource_version == v0


# --- invariant 16 — canonicalizer round-trip stability ------------------------------------- #

def test_canonical_is_round_trip_stable():
    # The precondition test 7's recompute rests on: re-canonicalizing a parsed canonical string is a
    # fixed point, across the descriptor value types (strings, the oracle_min int, nested string maps).
    for descriptor in (
        {"oracle_min": 2, "members": [{"name": "Z", "kind": "monolingual", "dir": "d", "hash": "sha256:x"}]},
        {"case_fold": "lower", "accent_fold": {"from": "àé", "to": "ae"}},
        {"b": 1, "a": 2, "nested": {"y": [3, 2, 1], "x": "ünïcödé"}},
    ):
        once = _canonical(descriptor)
        assert _canonical(json.loads(once)) == once


# --- invariant 17 — descriptor keys == ops' inputs (no hollow version) --------------------- #

def test_normalizer_descriptor_keys_are_exactly_the_fold_ops_inputs():
    # chunk_key reads {case_fold, accent_fold}; probe_forms reads {accent_fold}; their union is
    # exactly the descriptor's keys — so the normalizer version hashes precisely what is applied. A
    # field hashed-but-unused (a hollow version) or used-but-unhashed turns this red.
    policy = NormalizationPolicy(case_fold="lower", accent_fold={"from": "à", "to": "a"})
    assert set(policy.descriptor().keys()) == {"case_fold", "accent_fold"}


# --- invariant 18 — stale-class wire values pinned at the serialization site --------------- #

def test_stale_class_wire_values_are_pinned_at_the_serialization_site(fake_assets):
    cfg, _ = fake_assets
    rec = ResourceLineage.build(cfg).to_json()
    # the persisted literals S4.4 writes + S8.1 routes on — pinned at the EMITTED record, not the
    # bare constant (which would only restate its own literal). Mirrors test_atom_store.py's
    # env["stale_class"] == "atom-stream". A discriminator rename drifts the wire value while
    # distinctness (5) / diffability (14) / version-binding (7) all stay green — this catches it.
    assert rec["resource"]["stale_class"] == "resource-set"
    assert rec["normalizer"]["stale_class"] == "normalization-policy"
