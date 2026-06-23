"""Prompt-templating machinery: namespaced context, StrictUndefined, and the separability bite.

The OCR template is the first consumer. Two separability concerns are distinct:

  - **book-identity** separability — the template bakes no *book* identity; rendered under the
    synthetic book, no PLL identity string appears and the synthetic identity does. Proven here
    against the real synthetic fixture.
  - **language-baking** separability — the template body bakes no *language* specifics either;
    rendered against a hand-built foreign language context, the Italian accents/display name are
    absent and the foreign ones appear. A full non-Italian *book* fixture is BR-002 (deferred to
    M4b, where cleanup defines what it must differ on); the template body's genericity does not
    need that fixture — a foreign context dict proves it now.
"""

from __future__ import annotations

import pytest
from jinja2 import UndefinedError

from engine.config.loader import load_book
from engine.contracts.markers import SENTINEL_BLANK
from engine.prompts.templating import PROMPTS_DIR, PromptTemplate, build_prompt_context


def _render_ocr(book_id="synthetic", **overrides) -> str:
    tmpl = PromptTemplate.load("ocr")
    ctx = build_prompt_context(load_book(book_id))
    ctx.update(overrides)  # a test may swap a whole namespace (book/language) wholesale
    return tmpl.render(**ctx, blank_sentinel=SENTINEL_BLANK)


def test_template_file_is_profile_resident_and_loadable():
    # validate-bindings: the machinery resolves templates from the shared profiles/ tree, and the
    # OCR template actually exists there (not shape-asserted — load() reads the file).
    assert PROMPTS_DIR.name == "prompts" and PROMPTS_DIR.parent.name == "profiles"
    assert (PROMPTS_DIR / "ocr.txt.j2").is_file()
    assert PromptTemplate.load("ocr").name == "ocr"


def test_load_missing_template_is_a_clean_error():
    with pytest.raises(FileNotFoundError, match="prompt template not found"):
        PromptTemplate.load("no_such_template")


def test_build_prompt_context_is_namespaced():
    ctx = build_prompt_context(load_book("per_la_liberta"))
    assert set(ctx) == {"book", "language"}
    # book namespace = the manifest's free prompt_context verbatim (no language_name)
    assert ctx["book"]["book_title"] == "Per la libertà!"
    assert "language_name" not in ctx["book"]
    # language namespace = cross-title facts from the profile
    assert ctx["language"]["display_name"] == "Italian"
    assert ctx["language"]["accent_inventory"] == ["à", "è", "ì", "ò", "ù", "é"]


def test_strict_undefined_raises_on_missing_context_key():
    tmpl = PromptTemplate.load("ocr")
    # language present, but book missing every key it references → hard render error, not blanks.
    with pytest.raises(UndefinedError):
        tmpl.render(
            book={}, language={"display_name": "X", "accent_inventory": ["ñ"]},
            blank_sentinel=SENTINEL_BLANK,
        )


def test_no_book_identity_leaks_under_synthetic_render():
    rendered = _render_ocr("synthetic")
    # PLL book identity must be absent — the template pulled identity from book.* (synthetic's).
    for pll in ("Per la libertà", "Crespi", "1913"):
        assert pll not in rendered, f"PLL identity {pll!r} leaked from the template"
    # ...and the synthetic identity is present, proving the facts are interpolated, not hardcoded.
    for syn in ("Libro di Prova", "Autore Sintetico", "1901"):
        assert syn in rendered


def test_template_body_bakes_no_language_specifics():
    # Hand-built foreign context (no non-Italian *book* needed — BR-002): if the template body
    # baked Italian, these Italian facts would survive a foreign render. They must not.
    rendered = _render_ocr(
        "synthetic",
        book={"book_title": "Aklat", "author": "May-akda", "year": 1801},
        language={"display_name": "Tagalog", "accent_inventory": ["ñ"]},
    )
    assert "Tagalog" in rendered and "ñ" in rendered
    assert "Italian" not in rendered
    for it_accent in ("à", "è", "ì", "ò", "ù", "é"):
        assert it_accent not in rendered, "an Italian accent is baked into the template body"
