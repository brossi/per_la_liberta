"""Config loader: resolution of the real PLL manifest, schema enforcement, override.

These prove the three things the loader exists to do — (1) wire manifest + profiles into a
typed ``ResolvedConfig`` carrying the real constants M2 ``validate`` will read, (2) reject
malformed hand-edited config with a clear error, (3) apply the one supported override mode.
No live PLL artifacts are touched; the inputs are the committed engine config files.
"""

from __future__ import annotations

import json

import pytest

from engine.config import loader
from engine.config.loader import ConfigError, load_book

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
    assert lp.spacy_distribution == "it-core-news-lg"
    assert "the" in lp.english_markers and "correct" in lp.english_markers
    assert "il" in lp.skip_words
    assert lp.consonant_alphabet == "bcdfghjklmnpqrstvwxyz"
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
