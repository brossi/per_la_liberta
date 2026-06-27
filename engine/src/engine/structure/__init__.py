"""``engine.structure`` — the document-structure substrate (concerns A/B/C, three layers).

A book/language-agnostic model of document structure: L1 immutable addressed atoms → L2
versioned block projections (the durable ``node_id`` catalogue) → L3 spans / relations /
cross-language alignment (ENGINE_STRUCTURE_PLAN §2–§3). The core here carries **no** language,
ordinal, or book-structure literal — heading grammar, matter labels, and numbering are data in
the structure profile + the per-book structure map, never code (invariant I4; the S0.2 neutrality
guard makes that a standing assertion). The atom/projection models, the recognizer, the persisted
stores, and governance land milestone by milestone (ENGINE_STRUCTURE_TASKS S1–S11); this package
is the S0.1 skeleton — the schema-version constants and the fixed artifact locations everything
else pins to.
"""

from __future__ import annotations

from engine.structure.artifacts import (
    ATOM_STORE_SCHEMA_VERSION,
    ATOMS_AREA,
    ATOMS_SUBDIR,
    RELATION_STORE_SCHEMA_VERSION,
    RELATIONS_FILENAME,
    STRUCTURE_MAP_FILENAME,
    STRUCTURE_MAP_SCHEMA_VERSION,
    atoms_dir,
    relations_path,
    structure_map_path,
)
from engine.structure.atoms import (
    PROCESSING_SCOPE_EXCLUDED,
    PROCESSING_SCOPE_INCLUDED,
    Atom,
    AtomDerivation,
    Geom,
    duplicate_atom_ids,
)
from engine.structure.capture import (
    PAGE_UNMAPPED,
    align_streams,
    assert_capture_tiles,
    build_canonical,
    capture_witness,
)
from engine.structure.classify import (
    DEGENERATE_CLASSIFIER_NAME,
    UNKNOWN,
    BlockClassification,
    BlockClassifier,
    DegenerateBlockClassifier,
)
from engine.structure.roundtrip import (
    ReversibleTransform,
    apply_forward,
    apply_inverse,
    hash_raw,
    is_reversible,
    reconstruct_raw,
    verify_atom_roundtrip,
)

__all__ = [
    "ATOM_STORE_SCHEMA_VERSION",
    "STRUCTURE_MAP_SCHEMA_VERSION",
    "RELATION_STORE_SCHEMA_VERSION",
    "ATOMS_AREA",
    "ATOMS_SUBDIR",
    "STRUCTURE_MAP_FILENAME",
    "RELATIONS_FILENAME",
    "atoms_dir",
    "structure_map_path",
    "relations_path",
    # S1.1 — L1 atom model (concern A capture)
    "Atom",
    "Geom",
    "AtomDerivation",
    "duplicate_atom_ids",
    "PROCESSING_SCOPE_INCLUDED",
    "PROCESSING_SCOPE_EXCLUDED",
    # S0.4 — block-classifier seam (concern A typing)
    "BlockClassifier",
    "BlockClassification",
    "DegenerateBlockClassifier",
    "UNKNOWN",
    "DEGENERATE_CLASSIFIER_NAME",
    # S1.2 — raw/normalized round-trip floor (concern A capture)
    "hash_raw",
    "reconstruct_raw",
    "ReversibleTransform",
    "apply_forward",
    "apply_inverse",
    "is_reversible",
    "verify_atom_roundtrip",
    # S1.3a — raw addressed capture (per-witness streams + canonical projection)
    "capture_witness",
    "build_canonical",
    "align_streams",
    "assert_capture_tiles",
    "PAGE_UNMAPPED",
]
