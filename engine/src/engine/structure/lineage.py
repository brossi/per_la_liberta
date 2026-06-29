"""S3.0 resource + normalization-policy lineage — the input-versioning value object.

Where the atom store / structure map / relation store version *persisted layers*, this versions
the **inputs** a build consumes (S3.0 R3; ``docs/s3_0_plan.md`` D-C/D-E/D-G): the profile-declared
resources (the frequency dictionary + each period dictionary) and the pre-lookup fold policy. Both
collapse to content-derived ``sha256:`` versions held in one :class:`ResourceLineage`, under **two
distinct stale classes** (``structure.artifacts``) so governance (S8.1) routes a *resource swap →
re-segment* and a *normalizer change → re-derive offsets* as different repairs.

The two version producers:

- **Resources** — a content hash of the bytes each member declares, resolved through the profile
  (``require_asset``) and the member's ``index.json`` ``chunks[*].file`` set (never a glob): a
  member swap/add/remove, a re-OCR of the same source, or an ``oracle_min`` change all move the
  version; an undeclared stray file does not. Fail-loud — a declared-but-absent file or a member
  with no ``index.json`` raises ``MissingInputError``, never a silent partial hash. Two tiers: a
  rolled-up ``resource_version`` plus the per-member hashes that produced it (so a diff localizes to
  "which dictionary changed").
- **Normalizer** — a hash of ``NormalizationPolicy.descriptor()`` (``{case_fold, accent_fold}``),
  exactly the axes the fold ops apply.

Determinism (D-G): descriptors are canonical JSON (``_canonical``) hashed via ``_sha256_bytes``;
members are sorted by name and each member's files by chunk key, so reordering the profile's
dictionary list does not move the version. ``to_json`` emits the *parsed* descriptors (the header
fragment S4.4 embeds); the stored canonical strings are the exact hashed bytes, and the version↔
descriptor binding is re-established by re-canonicalizing (invariant 7), valid because ``_canonical``
is round-trip stable (invariant 16). No ``from_json`` / stale-compare here — that loader is S8.1's.

Engine-agnostic: this module reads paths and fold tables from the profile and carries no language,
ordinal, or book-structure literal (the S0.2 structure-neutrality guard scans it).

Scaffold stub (S3.0.3 / #25): ``_sha256_bytes``, ``_canonical``, and ``ResourceLineage.build`` /
``to_json`` are importable real signatures raising ``NotImplementedError``; the hashing and
canonicalization land across S3.0.5 (#27). ``_canonical`` is stubbed here (not only in #27) so the
red battery's recompute-binding and canonicalizer-idempotence invariants import without a
collection-time error.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from engine.structure.artifacts import RESOURCE_LINEAGE_SCHEMA_VERSION

if TYPE_CHECKING:  # the real build() reads only cfg.language; typed here without a runtime import
    from engine.config.models import ResolvedConfig


def _sha256_bytes(data: bytes) -> str:
    """``sha256:<hex>`` over raw ``data`` bytes — the single digest producer for the lineage.

    Distinct from ``structure.roundtrip.hash_raw`` (which encodes a ``str`` and so would hide a
    CRLF/encoding change behind newline translation): resources are hashed as bytes, and the
    canonical-JSON descriptor path feeds its UTF-8-encoded string through this same producer.
    Raises ``NotImplementedError`` until S3.0.5 (#27).
    """
    raise NotImplementedError("_sha256_bytes lands in S3.0.5 (#27)")


def _canonical(obj: object) -> str:
    """Canonical JSON for ``obj`` — ``sort_keys``, ``ensure_ascii=False``, compact separators.

    The one serializer behind both the stored descriptor string and the hashed bytes, so the two
    cannot diverge. Round-trip stable (``_canonical(json.loads(_canonical(d))) == _canonical(d)``),
    the precondition the recompute-binding rests on. Raises ``NotImplementedError`` until S3.0.5
    (#27).
    """
    raise NotImplementedError("_canonical lands in S3.0.5 (#27)")


@dataclass(frozen=True, slots=True)
class ResourceLineage:
    """Versioned lineage of a build's resources + normalization policy (two stale classes).

    Each descriptor is held as its **canonical JSON string** — immutable and by construction the
    exact bytes hashed, so a stored descriptor cannot drift from its version. ``to_json`` parses
    them back to dicts for the embeddable header fragment. Build via :meth:`build`; there is no
    ``from_json`` / stale-compare (that is S8.1's loader).
    """

    resource_version: str        # "sha256:…" over the resource descriptor
    resource_descriptor: str     # canonical JSON: {oracle_min, members:[{name,kind,dir,hash}, …]}
    resource_stale_class: str
    normalizer_version: str      # "sha256:…" over the normalizer descriptor
    normalizer_descriptor: str   # canonical JSON: {case_fold, accent_fold}
    normalizer_stale_class: str
    schema_version: int = RESOURCE_LINEAGE_SCHEMA_VERSION

    @classmethod
    def build(cls, cfg: "ResolvedConfig") -> "ResourceLineage":
        """Resolve + hash the profile-declared resources and the fold policy into a lineage.

        Reads only ``cfg.language`` (the frequency dict, the period dictionaries + ``oracle_min``,
        and ``case_fold``/``accent_fold``). Raises ``NotImplementedError`` until S3.0.5 (#27);
        ``MissingInputError`` on a declared-but-absent file / a member without an ``index.json``
        once implemented.
        """
        raise NotImplementedError("ResourceLineage.build lands in S3.0.5 (#27)")

    def to_json(self) -> dict:
        """The embeddable header fragment: schema version + the resource/normalizer tiers, each as
        ``{version, stale_class, descriptor}`` with the descriptor parsed back to a dict.

        Raises ``NotImplementedError`` until S3.0.5 (#27).
        """
        raise NotImplementedError("ResourceLineage.to_json lands in S3.0.5 (#27)")
