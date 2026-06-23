"""Config loader: resolution of the real PLL manifest, schema enforcement, override.

These prove the three things the loader exists to do — (1) wire manifest + profiles into a
typed ``ResolvedConfig`` carrying the real constants M2 ``validate`` will read, (2) reject
malformed hand-edited config with a clear error, (3) apply the one supported override mode.
No live PLL artifacts are touched; the inputs are the committed engine config files.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from engine.config import loader
from engine.config.loader import ConfigError, load_book
from engine.lang.registry import UnknownLanguageError, get_language_plugin

REAL_BOOKS = loader.DEFAULT_BOOKS_DIR
REAL_PROFILES = loader.DEFAULT_PROFILES_DIR


def test_resolves_real_pll_constants():
    cfg = load_book("per_la_liberta")

    # structure (the M2 validate contract)
    s = cfg.structure
    assert (s.h2_min, s.h3_count, s.content_units) == (3, 57, 58)
    assert s.retention_min == 0.60
    assert s.foreign_char_max == 0.005
    assert s.word_quality_high_severity_max == 0
    assert tuple((p.name, p.chapters) for p in s.parts) == (
        ("Parte Prima", 24),
        ("Parte Seconda", 33),
    )

    # language profile (validate + later oracle)
    lp = cfg.language
    assert cfg.language_id == "it" == lp.language_id
    assert lp.spacy_model == "it_core_news_lg"
    assert "the" in lp.english_markers and "correct" in lp.english_markers
    assert "il" in lp.skip_words
    assert lp.consonant_alphabet == "bcdfghjklmnpqrstvwxyz"
    # coverage is a structured literal-character allowlist (no regex).
    assert lp.coverage.ascii_letters is True and lp.coverage.digits is True
    assert "à" in lp.coverage.letters and "É" in lp.coverage.letters
    assert "«" in lp.coverage.punctuation and "…" in lp.coverage.punctuation
    assert lp.accent_optional is True
    assert lp.oracle_min == 2
    assert {d.name for d in lp.period_dictionaries} == {
        "Zingarelli 1922", "Edgren 1901", "Hoare 1915"
    }

    # scan profile (page-marker pattern read by M2; subs by M3/M4)
    assert cfg.source_noise.page_marker_artifact_pattern == r"\d+\s+[35][EI]:?"
    assert ("cbe", "che") in cfg.source_noise.substitution_rules
    assert cfg.source_noise.boundary_substitutions == {"i": ["r", "e"]}

    # edition + typeface (M3)
    assert cfg.manifest.edition.author == "Cesare Crespi (1913)"
    assert cfg.manifest.edition.site_base.endswith("/PER_LA_LIBERTA")
    assert cfg.typeface.display_family == "Spectral"
    assert cfg.typeface.body_family == "Fraunces"


def _write_book(tmp_path, name, manifest: dict):
    book_dir = tmp_path / "books" / name
    book_dir.mkdir(parents=True)
    (book_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path / "books"


def test_schema_rejects_missing_required_field(tmp_path):
    bad = json.loads((REAL_BOOKS / "per_la_liberta" / "manifest.json").read_text())
    del bad["structure"]
    books = _write_book(tmp_path, "bad", bad)
    with pytest.raises(ConfigError, match="schema validation"):
        load_book("bad", books_dir=books, profiles_dir=REAL_PROFILES)


def test_schema_rejects_wrong_type(tmp_path):
    bad = json.loads((REAL_BOOKS / "per_la_liberta" / "manifest.json").read_text())
    bad["structure"]["h3_count"] = "fifty-seven"
    books = _write_book(tmp_path, "bad", bad)
    with pytest.raises(ConfigError, match="schema validation"):
        load_book("bad", books_dir=books, profiles_dir=REAL_PROFILES)


@pytest.mark.parametrize("missing", ["book_title", "author", "year"])
def test_prompt_context_requires_the_ocr_template_keys(tmp_path, missing):
    # The OCR template (profiles/prompts/ocr.txt.j2) hard-references book.book_title/author/year
    # under StrictUndefined. Pinning them in the manifest schema turns a forgotten key into a
    # clean ConfigError at *load* — not a late jinja2.UndefinedError at render time, which escapes
    # the CLI exception taxonomy as a raw traceback (the gap this closes).
    m = _real_manifest()
    m["id"] = "pc"
    del m["prompt_context"][missing]
    books = _write_book(tmp_path, "pc", m)
    with pytest.raises(ConfigError, match="schema validation"):
        load_book("pc", books_dir=books, profiles_dir=REAL_PROFILES)


def test_prompt_context_stays_extensible_beyond_the_required_three(tmp_path):
    # Only the three keys the OCR template consumes are required; prompt_context stays open for
    # the later prompts (subject/entities feed triage/translate, pinned when they land). Dropping
    # a non-OCR key still loads — proving the requirement is exactly the three, not over-tightened.
    m = _real_manifest()
    m["id"] = "pcx"
    del m["prompt_context"]["subject"]
    books = _write_book(tmp_path, "pcx", m)
    cfg = load_book("pcx", books_dir=books, profiles_dir=REAL_PROFILES)
    assert "subject" not in cfg.manifest.prompt_context
    assert cfg.manifest.prompt_context["book_title"] == "Per la libertà!"


def test_override_replaces_profile_field(tmp_path):
    # A sibling book reusing the Italian profile but swapping the oracle threshold —
    # the one realistic override case the shallow-replace mode is built for.
    m = json.loads((REAL_BOOKS / "per_la_liberta" / "manifest.json").read_text())
    m["id"] = "ovr"
    m["overrides"] = {"language": {"oracle_min": 3}}
    books = _write_book(tmp_path, "ovr", m)

    base = load_book("per_la_liberta")
    overridden = load_book("ovr", books_dir=books, profiles_dir=REAL_PROFILES)
    assert base.language.oracle_min == 2
    assert overridden.language.oracle_min == 3


def test_missing_book_is_a_clean_error(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_book("nonexistent", books_dir=tmp_path, profiles_dir=REAL_PROFILES)


def _real_manifest() -> dict:
    return json.loads((REAL_BOOKS / "per_la_liberta" / "manifest.json").read_text())


def test_language_id_mismatch_is_rejected(tmp_path):
    # Manifest declares 'fr' but the referenced profile is 'it' — the loader guard fires.
    m = _real_manifest()
    m["language"] = "fr"
    books = _write_book(tmp_path, "mm", m)
    with pytest.raises(ConfigError, match="language mismatch"):
        load_book("mm", books_dir=books, profiles_dir=REAL_PROFILES)


def test_missing_profile_ref_is_a_clean_error(tmp_path):
    m = _real_manifest()
    m["profiles"]["language"] = "no_such_profile"
    books = _write_book(tmp_path, "mp", m)
    with pytest.raises(ConfigError, match="not found"):
        load_book("mp", books_dir=books, profiles_dir=REAL_PROFILES)


def test_profile_schema_guards_its_builder(tmp_path):
    # A malformed *profile* (not just the manifest) must fail validation — the only test
    # that exercises the profile-level schema path. A language profile missing oracle_min
    # would otherwise KeyError in the builder; the schema turns it into a clean ConfigError.
    prof = tmp_path / "profiles" / "languages"
    prof.mkdir(parents=True)
    lang = json.loads((REAL_PROFILES / "languages" / "italian_1900_1922.json").read_text())
    del lang["oracle_min"]
    (prof / "italian_1900_1922.json").write_text(json.dumps(lang), encoding="utf-8")
    books = _write_book(tmp_path, "bp", _real_manifest())
    with pytest.raises(ConfigError, match="schema validation"):
        load_book("bp", books_dir=books, profiles_dir=tmp_path / "profiles")


def test_override_is_validated_after_merge(tmp_path):
    # An override that violates the schema is caught — proving override happens before,
    # not after, validation.
    m = _real_manifest()
    m["id"] = "ovrbad"
    m["overrides"] = {"language": {"oracle_min": "two"}}  # wrong type
    books = _write_book(tmp_path, "ovrbad", m)
    with pytest.raises(ConfigError, match="schema validation"):
        load_book("ovrbad", books_dir=books, profiles_dir=REAL_PROFILES)


def test_override_replaces_list_field_wholesale(tmp_path):
    # The documented shallow-replace semantics: overriding a list swaps it whole, it does
    # not append. (This is the tradeoff vs the deferred per-field deep merge.)
    m = _real_manifest()
    m["id"] = "ovrlist"
    m["overrides"] = {
        "language": {
            "period_dictionaries": [
                {"name": "Only One", "kind": "monolingual", "dir": "dictionary/only_one"}
            ]
        }
    }
    books = _write_book(tmp_path, "ovrlist", m)
    cfg = load_book("ovrlist", books_dir=books, profiles_dir=REAL_PROFILES)
    assert [d.name for d in cfg.language.period_dictionaries] == ["Only One"]


def _stage_profiles(tmp_path) -> Path:
    """Copy the real profile tree into tmp so a single profile can be corrupted in place."""
    dst = tmp_path / "profiles"
    for sub in ("languages", "source_noise", "typefaces"):
        (dst / sub).mkdir(parents=True)
        for f in (REAL_PROFILES / sub).glob("*.json"):
            shutil.copy(f, dst / sub / f.name)
    return dst


def test_source_noise_schema_is_enforced(tmp_path):
    # Proves load_book validates the source-noise profile, not only the language one.
    prof = _stage_profiles(tmp_path)
    p = prof / "source_noise" / "bodoni_didone.json"
    data = json.loads(p.read_text())
    del data["substitution_rules"]
    p.write_text(json.dumps(data), encoding="utf-8")
    books = _write_book(tmp_path, "sn", _real_manifest())
    with pytest.raises(ConfigError, match="schema validation"):
        load_book("sn", books_dir=books, profiles_dir=prof)


def test_typeface_schema_is_enforced(tmp_path):
    # ...and the typeface profile (the third _validate call).
    prof = _stage_profiles(tmp_path)
    p = prof / "typefaces" / "spectral_fraunces.json"
    data = json.loads(p.read_text())
    del data["display_family"]
    p.write_text(json.dumps(data), encoding="utf-8")
    books = _write_book(tmp_path, "tf", _real_manifest())
    with pytest.raises(ConfigError, match="schema validation"):
        load_book("tf", books_dir=books, profiles_dir=prof)


def test_malformed_coverage_fails_schema(tmp_path):
    # The coverage object's shape is schema-enforced — a missing required sub-field is a clean
    # ConfigError, not a KeyError in the builder. (The set-membership design has no regex to be
    # malformed, so there is nothing deeper to guard.)
    prof = _stage_profiles(tmp_path)
    lp = prof / "languages" / "italian_1900_1922.json"
    data = json.loads(lp.read_text())
    del data["coverage"]["letters"]
    lp.write_text(json.dumps(data), encoding="utf-8")
    books = _write_book(tmp_path, "bad_cov", _real_manifest())
    with pytest.raises(ConfigError, match="schema validation"):
        load_book("bad_cov", books_dir=books, profiles_dir=prof)


def test_language_profile_requires_a_monolingual_period_dictionary(tmp_path):
    # adjudicate._build_oracle binds its membership oracle to a *monolingual* period dictionary
    # and raises if none — a bare ValueError that escapes the CLI exception taxonomy as a raw
    # traceback. The schema now enforces ≥1 monolingual member, so a profile declaring only
    # bilingual dicts fails at LOAD (ConfigError) instead. (Same defect class as the prompt_context
    # fix: a consumer requirement the contract didn't guarantee, failing late.) This also empirically
    # confirms the installed jsonschema enforces draft-2020-12 `contains`.
    prof = _stage_profiles(tmp_path)
    lp = prof / "languages" / "italian_1900_1922.json"
    data = json.loads(lp.read_text())
    data["period_dictionaries"] = [
        d for d in data["period_dictionaries"] if d["kind"] != "monolingual"
    ]
    assert data["period_dictionaries"], "fixture must keep bilingual dicts — testing 'no monolingual', not 'empty'"
    lp.write_text(json.dumps(data), encoding="utf-8")
    books = _write_book(tmp_path, "nomono", _real_manifest())
    with pytest.raises(ConfigError, match="schema validation"):
        load_book("nomono", books_dir=books, profiles_dir=prof)


def test_unimplemented_but_consistent_language_reaches_unknown_language_error(tmp_path):
    # The real joined path (not the monkeypatched CLI half): the loader is plugin-agnostic,
    # so a manifest+profile both declaring 'xx' load cleanly; the missing plugin only
    # surfaces at get_language_plugin.
    prof = _stage_profiles(tmp_path)
    lp = prof / "languages" / "italian_1900_1922.json"
    data = json.loads(lp.read_text())
    data["language_id"] = "xx"
    lp.write_text(json.dumps(data), encoding="utf-8")
    m = _real_manifest()
    m["language"] = "xx"
    books = _write_book(tmp_path, "xx", m)

    cfg = load_book("xx", books_dir=books, profiles_dir=prof)
    assert cfg.language_id == "xx"
    with pytest.raises(UnknownLanguageError):
        get_language_plugin(cfg.language_id)
