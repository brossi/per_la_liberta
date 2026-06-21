"""Asset binding: every asset the resolved config references must actually resolve.

The config carries asset *paths* as strings; nothing in the schema proves they point at a
real file. These tests close that gap — they would have caught the frequency-dictionary
path pointing at a nonexistent location. They assert hard (no skipif): a bare ``uv sync``
without ``--extra it`` should fail loudly here, not skip silently, because the only book is
Italian and cannot be processed without its model + dictionaries.
"""

from __future__ import annotations

import importlib.util

import pytest

from engine import paths
from engine.config.loader import load_book
from engine.lang import base
from engine.lang.italian import ItalianLanguagePlugin


def test_frequency_dictionary_resolves_to_a_file():
    cfg = load_book("per_la_liberta")
    p = paths.asset_path(cfg.language.frequency_dictionary)
    assert p.is_file(), f"frequency dictionary not found at {p}"


def test_period_dictionaries_resolve_to_dirs():
    cfg = load_book("per_la_liberta")
    for d in cfg.language.period_dictionaries:
        p = paths.asset_path(d.dir)
        assert p.is_dir(), f"period dictionary {d.name!r} not found at {p}"


def test_spacy_model_is_installed():
    cfg = load_book("per_la_liberta")
    model = cfg.language.spacy_model
    assert importlib.util.find_spec(model) is not None, (
        f"spaCy model {model!r} not installed; run `uv sync --extra it`"
    )


def test_load_spacy_caches_by_model_and_disable(monkeypatch):
    # Exercise the cache logic without the heavy model: a fresh cache + a fake spacy.load.
    monkeypatch.setattr(base, "_SPACY_PIPELINES", {})
    import spacy

    calls: list[tuple] = []

    def fake_load(model, disable=None):
        calls.append((model, tuple(disable or ())))
        return object()

    monkeypatch.setattr(spacy, "load", fake_load)
    plugin = ItalianLanguagePlugin()

    a = plugin.load_spacy("zz_fake_model")
    b = plugin.load_spacy("zz_fake_model")
    assert a is b and len(calls) == 1  # same (model, disable) → cached, loaded once

    c = plugin.load_spacy("zz_fake_model", disable=["ner"])
    assert c is not a and len(calls) == 2  # different disable → distinct pipeline


def test_load_spacy_missing_model_gives_actionable_error(monkeypatch):
    monkeypatch.setattr(base, "_SPACY_PIPELINES", {})
    import spacy

    def boom(model, disable=None):
        raise OSError("can't find model")

    monkeypatch.setattr(spacy, "load", boom)
    with pytest.raises(OSError, match="uv sync --extra"):
        ItalianLanguagePlugin().load_spacy("nope_model")


@pytest.mark.integration
def test_load_spacy_real_model_returns_pipeline():
    from spacy.language import Language

    cfg = load_book("per_la_liberta")
    nlp = ItalianLanguagePlugin().load_spacy(
        cfg.language.spacy_model, disable=["parser", "lemmatizer"]
    )
    assert isinstance(nlp, Language)
