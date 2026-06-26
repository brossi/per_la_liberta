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
]
