"""S3.0 resource + normalization-policy lineage — the red-first invariant battery.

Home of the S3.0 lineage battery (ENGINE_STRUCTURE_PLAN S3.0; ``docs/s3_0_plan.md`` §4). The
battery is built red-first and lands across the S3.0 build order (§5): this commit seats the
stale-class distinctness invariant (test 5) against the constants minted in ``structure/artifacts.py``
(#23); the resource/normalizer version, fold-op, fail-loud, determinism, and neutrality invariants
arrive with the surfaces they bind (#25 onward), each written to fail first on its own assertion.

Invariant 5 — two distinct stale classes (D-D). ``RESOURCE_STALE_CLASS`` and
``NORMALIZER_STALE_CLASS`` must differ from each other and from the one persisted-layer class that
exists after this task (``ATOM_STORE_STALE_CLASS``), so the lineage governance (S8.1) routes a
*resource swap → re-segment* and a *normalizer change → re-derive offsets* as **different** repairs
(§3.6). Red-proof: collapse the two classes to one literal, or alias either onto
``ATOM_STORE_STALE_CLASS``, and the set-size assertion goes red.

A second check here — ``test_resource_lineage_schema_version_is_a_positive_int`` — is a binding
sanity check on the new ``RESOURCE_LINEAGE_SCHEMA_VERSION`` constant (feedback_validate_bindings),
**not** one of the §4 numbered invariants. #25 adds invariants 1–4 and 6–17 alongside the surfaces
they bind and must **not** re-seat test 5 (it already lives here). The literal wire *values* of the
two stale classes are pinned at the serialization site — ``ResourceLineage.to_json()`` (#27),
mirroring ``test_atom_store.py``'s envelope pin — not against the bare constants here, where the
assertion would only restate its own literal.
"""

from __future__ import annotations

import engine.structure as structure


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
