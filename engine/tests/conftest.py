"""Shared pytest fixtures for the engine test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

ENGINE_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def engine_root() -> Path:
    """Absolute path to the engine/ package root (parent of src/, books/, profiles/)."""
    return ENGINE_ROOT
