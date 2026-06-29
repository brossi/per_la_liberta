"""Persisted structure-substrate artifacts: where each lives in the work tree, and the
independent schema version each carries.

The document-structure substrate writes three durable artifacts under a book's
``BookWorkspace`` (``books/<id>/work/``), one per layer of the L1→L2→L3 model
(ENGINE_STRUCTURE_PLAN §3.2):

- **atom store** — per-witness + canonical L1 atom streams, under ``data/atoms/*.json`` (§11.1);
- **structure map** — B's durable container/projection catalogue, ``structure_map.json`` at the
  work root (§11.2);
- **relation store** — the L3 graph + cross-language alignment, ``relations.json`` at the work
  root (§11.3).

Each layer is **independently versioned**: a schema change to one does not bump the others, so a
lineage stale-check can name *which* layer changed and route the right migration — three distinct
stale classes (ENGINE_STRUCTURE_TASKS M3; the stores land in S1.5 / S4.4 / S7.1c). This module is
the S0.1 skeleton: it fixes the locations and the version constants now; the stores, JSON schemas,
and lineage manifest that read them arrive with those later tasks.

Engine-agnostic by construction: artifact *names* and *layout* only — no language, ordinal, or
book-structure opinion (the recognizer and the structure profile carry that, never this core).
"""

from __future__ import annotations

from pathlib import Path

from engine.paths import BookWorkspace

# --- schema versions (independent per persisted layer — M3) ----------------------------- #

#: L1 atom-store schema version (per-witness + canonical streams). Bound by S1.5.
ATOM_STORE_SCHEMA_VERSION = 1
#: The L1 atom-store stale class — the M3 stale-class identifier the lineage governance (S8.1) routes
#: on, and the discriminator a persisted stream's envelope declares so a load can reject a file that
#: is structurally JSON but not an atom store. Distinct from the structure-map (B) and relation-store
#: (C) classes, so a schema change to one names *which* layer changed (§3.6). Bound by S1.5.
ATOM_STORE_STALE_CLASS = "atom-stream"
#: L2 structure-map schema version (containers/projections + lineage manifest). Bound by S4.4.
STRUCTURE_MAP_SCHEMA_VERSION = 1
#: L3 relation-store schema version (graph + cross-language alignment). Bound by S7.1c.
RELATION_STORE_SCHEMA_VERSION = 1

# --- fixed work-tree locations ---------------------------------------------------------- #

#: Workspace area + subdirectory the L1 atom streams live under (``<work>/data/atoms/``).
ATOMS_AREA = "data"
ATOMS_SUBDIR = "atoms"
#: Work-root filenames for the durable catalogue (B) and the relation graph (C). These sit at
#: the work root, not under an area, by design (§11.2/§11.3) — the top-level book artifacts.
STRUCTURE_MAP_FILENAME = "structure_map.json"
RELATIONS_FILENAME = "relations.json"


def atoms_dir(workspace: BookWorkspace) -> Path:
    """Directory holding the L1 atom streams (``<work>/data/atoms/``), containment-checked.

    Returns the path only; creating it is the atom store's job (S1.5), as with every other
    workspace path accessor.
    """
    return workspace.resolve(ATOMS_AREA, ATOMS_SUBDIR)


def structure_map_path(workspace: BookWorkspace) -> Path:
    """Path to the durable structure map (``<work>/structure_map.json``)."""
    return workspace.resolve_root(STRUCTURE_MAP_FILENAME)


def relations_path(workspace: BookWorkspace) -> Path:
    """Path to the relation store (``<work>/relations.json``)."""
    return workspace.resolve_root(RELATIONS_FILENAME)
