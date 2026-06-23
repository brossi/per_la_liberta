"""Invariant I8 — atomic / no-partial-output: every artifact a later step consumes is written
through an atomic helper (temp file + ``os.replace``), never a raw write a mid-write crash could
truncate into a file the next step then reads as *complete*. This is the assumption the I2 residual
rests on: a present internal artifact is never half-written, so a sibling step's read failure is
bug-class, not an expected error. Found violated in the post-M4a completeness audit (download and
ocr wrote their text witnesses with raw ``Path.write_text``); these controls keep it fixed.

Positive control: ``atomic_write_text`` round-trips and leaves no temp residue. Negative controls: a
forced failure leaves nothing half-written at the destination, and an AST scan forbids raw file
writes anywhere under ``steps/`` (the sanctioned writers live in ``util/jsonio.py``, excluded).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from engine.util.jsonio import atomic_write_text

_SRC = Path(__file__).resolve().parents[2] / "src" / "engine"
_STEPS = _SRC / "steps"


def test_atomic_write_text_roundtrips_and_leaves_no_tmp(tmp_path):
    target = tmp_path / "witness.txt"
    atomic_write_text(target, "héllo ⟨PAGE:1⟩\nworld")
    assert target.read_text(encoding="utf-8") == "héllo ⟨PAGE:1⟩\nworld"
    assert [p.name for p in tmp_path.iterdir()] == ["witness.txt"]  # no .tmp residue


def test_atomic_write_text_failure_leaves_nothing_partial(tmp_path):
    # Force a failure mid-write (f.write of a non-str raises TypeError): the destination must not
    # exist and the temp file must be cleaned up — the property the whole invariant turns on.
    target = tmp_path / "witness.txt"
    with pytest.raises(TypeError):
        atomic_write_text(target, 123)  # type: ignore[arg-type]
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def _open_mode(call: ast.Call) -> str | None:
    if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant) and isinstance(
        call.args[1].value, str
    ):
        return call.args[1].value
    for kw in call.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value
    return None


def _raw_writes_in(path: Path) -> list[str]:
    hits: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in ("write_text", "write_bytes"):
            hits.append(f"{path.name}:{node.lineno}: .{func.attr}(...)")
        elif isinstance(func, ast.Name) and func.id == "open":
            mode = _open_mode(node)
            if mode and any(c in mode for c in "wax"):
                hits.append(f"{path.name}:{node.lineno}: open(..., {mode!r})")
    return hits


def test_steps_have_python_files():
    # Guard against a vacuous green if the glob ever finds nothing.
    assert sorted(_STEPS.glob("*.py")), f"no step modules under {_STEPS}"


def test_no_raw_artifact_writes_in_steps():
    offenders: list[str] = []
    for f in sorted(_STEPS.glob("*.py")):
        offenders += _raw_writes_in(f)
    assert not offenders, (
        "raw (non-atomic) file write in a step — route artifacts through "
        "util.jsonio.atomic_write_{json,text} so a crash can't truncate a consumed artifact:\n"
        + "\n".join(offenders)
    )
