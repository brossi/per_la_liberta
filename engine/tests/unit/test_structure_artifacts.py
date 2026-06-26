"""``engine.structure`` S0.1 skeleton — schema-version constants + fixed artifact locations.

Asserts the package imports, the three persisted layers each expose an independent integer
schema version, and the artifact accessors resolve to their pinned work-tree locations *inside*
the workspace (ENGINE_STRUCTURE_PLAN §11.1–§11.3): atoms under the ``data`` area, the structure
map and relations at the work root. The containment guard on ``resolve_root`` itself (the
work-root resolver these accessors ride on) is exercised in ``test_workspace.py``, where it lives.
"""

from __future__ import annotations

import pytest

import engine.structure as structure
from engine.paths import BookWorkspace

VERSION_NAMES = (
    "ATOM_STORE_SCHEMA_VERSION",
    "STRUCTURE_MAP_SCHEMA_VERSION",
    "RELATION_STORE_SCHEMA_VERSION",
)


def test_structure_package_imports():
    assert structure.__doc__  # a real package, not an empty namespace


@pytest.mark.parametrize("name", VERSION_NAMES)
def test_each_layer_has_an_independent_positive_int_version(name):
    version = getattr(structure, name)
    # bool is an int subclass — exclude it so a stray True/False can't pass as a version.
    assert isinstance(version, int) and not isinstance(version, bool)
    assert version >= 1


def test_the_three_versions_are_independently_addressable():
    # M3: each layer's schema version is its own module-level name, so bumping one never moves
    # another. Their *values* coincide at v1 — a value-distinctness assertion would be hollow — so
    # the real invariant is that all three are present, distinct names on the package's public
    # surface, independently referenceable. That is what lets S1.5/S4.4/S7.1c bump one in isolation.
    assert len(set(VERSION_NAMES)) == 3                          # three distinct names, not aliases
    assert set(VERSION_NAMES) <= set(structure.__all__)          # each is part of the exported API
    assert all(hasattr(structure, n) for n in VERSION_NAMES)     # each resolves to its own binding


def test_atoms_dir_is_under_the_data_area(tmp_path):
    ws = BookWorkspace.for_book("demo", tmp_path)
    p = structure.atoms_dir(ws)
    assert p == ws.data / "atoms"
    assert p.is_relative_to(ws.root)


def test_structure_map_is_at_the_work_root(tmp_path):
    ws = BookWorkspace.for_book("demo", tmp_path)
    p = structure.structure_map_path(ws)
    assert p == ws.root / "structure_map.json"
    assert p.is_relative_to(ws.root)
    # at the root, NOT nested under an area — the §11.2 placement
    assert p.parent == ws.root


def test_relations_is_at_the_work_root(tmp_path):
    ws = BookWorkspace.for_book("demo", tmp_path)
    p = structure.relations_path(ws)
    assert p == ws.root / "relations.json"
    assert p.is_relative_to(ws.root)
    assert p.parent == ws.root


def test_the_three_artifact_locations_are_distinct(tmp_path):
    ws = BookWorkspace.for_book("demo", tmp_path)
    locations = {
        structure.atoms_dir(ws),
        structure.structure_map_path(ws),
        structure.relations_path(ws),
    }
    assert len(locations) == 3
