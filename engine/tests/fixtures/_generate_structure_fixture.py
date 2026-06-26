"""Dev-time generator for the trivial structure fixture. NOT a test (leading underscore) and
NOT run at test time.

Reuses the golden-generator pattern (``engine/tests/golden/_generate_*_fixture.py``) but lives
here under ``tests/fixtures/`` and writes a *fixture*, never a golden: the structure substrate
has **no live referent**, so a hand-authored synthetic artifact is a fixture /
reference-integrity target, not a parity golden (ENGINE_STRUCTURE_PLAN §9;
``feedback_no_cheating_results`` — a synthetic artifact wearing a "golden" badge invites invented
expected values). It exists to give the S0.3 tier spine (``test_structure_tiers.py``) a trivial
artifact that round-trips and whose declared ``schema_version`` stays bound to the live constant.

The fixture is deliberately minimal — a schema-version header and a self-describing note. The real
structure-map schema is S4.4; this MUST NOT anticipate it.

Refresh (only after a deliberate ``STRUCTURE_MAP_SCHEMA_VERSION`` bump):

    uv run python tests/fixtures/_generate_structure_fixture.py
"""

from __future__ import annotations

import json
from pathlib import Path

import engine.structure as structure

FIXTURES_DIR = Path(__file__).resolve().parent
OUT = FIXTURES_DIR / "structure" / "trivial_structure_map.json"


def build_fixture() -> dict:
    """The trivial fixture, ``schema_version`` derived from the live S0.1 constant.

    Deriving (rather than hard-coding) the version is the point: the committed fixture stays bound
    to ``STRUCTURE_MAP_SCHEMA_VERSION``, and the reference-integrity tier fails the moment the
    constant is bumped without a refresh here.
    """
    return {
        "schema_version": structure.STRUCTURE_MAP_SCHEMA_VERSION,
        "_placeholder": (
            "S0.3 tier-spine fixture — exercises the fixture/round-trip/reference-integrity/"
            "negative tiers only; the real structure-map schema is S4.4 and is not anticipated here."
        ),
    }


def render() -> str:
    """The exact file content the committed fixture must equal — the single source of the
    serialization format, shared by ``main`` (which writes it) and the byte-exact binding test
    (which asserts the committed file equals it). Keeping one renderer is what lets the test catch
    *formatting* drift, not just content drift.
    """
    return json.dumps(build_fixture(), indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(), encoding="utf-8")
    print(
        f"Wrote trivial structure fixture (schema_version="
        f"{structure.STRUCTURE_MAP_SCHEMA_VERSION}) → {OUT.relative_to(FIXTURES_DIR.parents[1])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
