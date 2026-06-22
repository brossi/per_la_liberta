"""Config dataclasses — the typed surface the orchestrator threads into steps.

These are *dumb data holders*: a faithful 1:1 transcription of the book/scan/language
constants the live pipeline hardcodes, reorganised per ``engine/docs/constant_inventory.md``
(the M1 acceptance checklist). They carry no behaviour and no field without an inventory
destination. ``loader.py`` builds them; steps read them.

``ResolvedConfig`` = ``BookManifest`` ⊕ ``LanguageProfile`` ⊕ ``SourceNoiseProfile`` ⊕
``TypefaceProfile`` (plan §"Config model"). Fields with an imminent consumer (``Structure``
and the validate-relevant ``LanguageProfile``/``SourceNoiseProfile`` fields feed M2's ``validate``)
are typed precisely; ``prompt_context`` stays a free dict because its keys are defined by the
prompt templates ported in M4, not knowable now.
"""

from __future__ import annotations

from dataclasses import dataclass


# --- manifest sub-objects -------------------------------------------------- #

@dataclass(frozen=True, slots=True)
class Source:
    """One OCR/scan witness (``manifest.sources[]``; consumed by download in M4a)."""

    role: str
    label: str
    ia_item_id: str
    url: str | None = None


@dataclass(frozen=True, slots=True)
class ScanFacts:
    """Book-specific scan facts (``manifest.scan``; consumed by ocr/typeset in M3–M4a)."""

    pdf: str
    page_image_template: str
    leaf_offset: int
    last_scan_page_default: int


@dataclass(frozen=True, slots=True)
class PartStructure:
    name: str
    chapters: int


@dataclass(frozen=True, slots=True)
class Structure:
    """Header-count contract + validation thresholds (``manifest.structure``; M2 ``validate``)."""

    h2_min: int
    h3_count: int
    parts: tuple[PartStructure, ...]
    content_units: int
    retention_min: float
    foreign_char_max: float
    word_quality_high_severity_max: int


@dataclass(frozen=True, slots=True)
class Edition:
    """Bibliographic metadata + deploy base (``manifest.edition``; consumed by typeset in M3)."""

    title_it: str
    subtitle_it: str
    subtitle_en: str
    author: str
    colophon: str
    ia_item_id: str
    site_base: str


@dataclass(frozen=True, slots=True)
class BookManifest:
    schema_version: int
    id: str
    title: str
    language_id: str
    profile_refs: dict  # {"language": <id>, "source_noise": <id>, "typeface": <id>}
    sources: tuple[Source, ...]
    scan: ScanFacts
    structure: Structure
    edition: Edition
    prompt_context: dict  # free-form; keys defined by the M4 prompt templates


# --- shared profiles ------------------------------------------------------- #

@dataclass(frozen=True, slots=True)
class PeriodDictionary:
    """One period dictionary for the ≥N-of-M membership oracle (M6 consumer)."""

    name: str
    kind: str  # "monolingual" | "bilingual"
    dir: str   # assets-relative chunk dir


@dataclass(frozen=True, slots=True)
class CoverageSpec:
    """What counts as *in-script* for validate's char-coverage check — a literal-character
    allowlist, deliberately **not** a regex. ``ascii_letters``/``digits`` toggle the a–zA–Z /
    0–9 ranges (a non-Latin script turns ASCII off); ``letters`` and ``punctuation`` are
    verbatim character lists (the script's letters beyond ASCII, and the tolerated typographic
    punctuation). The check turns this into a ``frozenset`` and tests membership, so there is no
    regex syntax, escaping, or accidental-range surface for a book author to get wrong.
    Whitespace is always in-script (the check filters it before testing)."""

    ascii_letters: bool
    digits: bool
    letters: str
    punctuation: str


@dataclass(frozen=True, slots=True)
class LanguageProfile:
    """Language knowledge shared across books in the same language/era.

    The word-quality fields (``english_markers``, ``skip_words``, ``consonant_alphabet``),
    ``coverage`` (char-coverage), and ``spacy_model``/``frequency_dictionary`` are read by M2
    ``validate``; the period dictionaries + ``oracle_min`` feed the M6 membership oracle.
    """

    language_id: str
    spacy_model: str
    spacy_distribution: str
    frequency_dictionary: str
    english_markers: tuple[str, ...]
    skip_words: tuple[str, ...]
    consonant_alphabet: str
    coverage: CoverageSpec
    accent_optional: bool
    period_dictionaries: tuple[PeriodDictionary, ...]
    oracle_min: int


@dataclass(frozen=True, slots=True)
class SourceNoiseProfile:
    """How the *source scan* degrades — the OCR-noise fingerprint of the typeface the
    original book was printed in (e.g. Bodoni/Didone's ``c``/``e`` ambiguity).

    This is an **input** concern: it drives cleanup's correction of OCR errors, and has
    nothing to do with how the *edition* is rendered (that is ``TypefaceProfile``). The
    engine ships no opinion here — a book supplies the noise profile matching its own scan.

    ``page_marker_artifact_pattern`` is read by M2 ``validate``; the substitution tables
    and ``page_marker_format`` are consumed by reconcile/cleanup in M3–M4b.
    ``noise_line_pattern`` is intentionally deferred to M4b (cleanup) — its only consumer —
    to avoid carrying an unverified escaped regex through M1.
    """

    name: str
    substitution_rules: tuple[tuple[str, str], ...]
    boundary_substitutions: dict  # {"i": ["r", "e"]}
    page_marker_artifact_pattern: str
    page_marker_format: str


@dataclass(frozen=True, slots=True)
class TypefaceProfile:
    """Output-edition typeface facts (consumed by typeset in M3).

    Deliberately thin: asset resolution / CSS version-hashing semantics are M3's to
    define, so M1 carries only the irreducible facts (the two families + the stylesheet
    filename). M3 extends this rather than reshaping a speculative model.
    """

    name: str
    display_family: str
    body_family: str
    css_filename: str


# --- the threaded object --------------------------------------------------- #

@dataclass(frozen=True, slots=True)
class ResolvedConfig:
    book_id: str
    manifest: BookManifest
    language: LanguageProfile
    source_noise: SourceNoiseProfile
    typeface: TypefaceProfile

    @property
    def language_id(self) -> str:
        return self.manifest.language_id

    @property
    def structure(self) -> Structure:
        return self.manifest.structure
