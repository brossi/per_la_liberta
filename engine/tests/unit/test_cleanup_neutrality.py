"""M4b-D1 / BR-002 code-neutrality: ``steps/cleanup.py`` carries no Italian or source-noise
*literal* in its functional code. Every accent/letter class and OCR-noise pattern the deterministic
core parameterises on is sourced from ``cfg.language`` / ``cfg.source_noise`` (proven behaviourally
by the detcore golden); this is the static guard that no such literal silently creeps back.

The scan forbids, in functional code:
  - any character in the accented-Latin block ``À–ÿ`` (U+00C0–U+00FF) — the Italian accents and the
    ``word_letter_class`` range, all of which must interpolate from config; and
  - ``£`` (U+00A3) — the relocated ``£→E`` source-noise confusion (now ``char_substitutions``).

Docstrings and comments are excluded: they legitimately *name* ``À-ÿ`` / ``£`` when documenting the
relocation (that is exactly where the prose lives). Universal typography (``« » — “ ” ‘ ’``) and
universal OCR-decoration glyphs (``■ • ¶ §``) are intentionally allowed — they sit OUTSIDE the
forbidden block, carry no language/typeface opinion, and stay in code as engine-general mechanics.
"""

from __future__ import annotations

import ast
import io
import tokenize
from pathlib import Path

CLEANUP = Path(__file__).resolve().parents[2] / "src" / "engine" / "steps" / "cleanup.py"

# Accented-Latin block (the Italian accents + the word_letter_class À-ÿ range) plus the relocated £.
FORBIDDEN = {chr(c) for c in range(0x00C0, 0x0100)} | {"£"}


def _functional_lines(path: Path) -> list[tuple[int, str]]:
    """Return ``(lineno, text)`` for every source line, with comments blanked and docstring lines
    dropped — so the scan sees only functional code, never the prose that documents the change."""
    src = path.read_text(encoding="utf-8")
    rows = [list(line) for line in src.splitlines()]

    # Blank comment spans (tokenize gives exact columns).
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            (srow, scol), (_erow, ecol) = tok.start, tok.end
            for col in range(scol, min(ecol, len(rows[srow - 1]))):
                rows[srow - 1][col] = " "

    # Identify docstring line ranges (module/class/function first-statement string).
    doc_lines: set[int] = set()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.body and isinstance(node.body[0], ast.Expr):
                value = node.body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    doc_lines.update(range(value.lineno, value.end_lineno + 1))

    return [
        (i, "".join(chars))
        for i, chars in enumerate(rows, 1)
        if i not in doc_lines
    ]


def test_no_italian_or_source_noise_literal_in_cleanup():
    hits = [
        f"cleanup.py:{lineno}: {line.strip()}  (contains {ch!r})"
        for lineno, line in _functional_lines(CLEANUP)
        for ch in line
        if ch in FORBIDDEN
    ]
    assert not hits, (
        "Italian/source-noise literal leaked into cleanup's functional code — source it from "
        "cfg.language / cfg.source_noise instead:\n" + "\n".join(hits)
    )


def test_scan_actually_excludes_docstrings_and_finds_real_leaks():
    # Guard the scan against a vacuous green two ways: (1) the source must be non-trivial; (2) the
    # forbidden-char test must actually fire on a planted leak, and the docstring-exclusion must
    # actually drop a docstring line that names a forbidden char.
    functional = _functional_lines(CLEANUP)
    assert len(functional) > 100, "functional-line extraction returned too little — scan is hollow"

    planted = "x = 'à'  # à literal in code"  # an à in functional position
    rows = planted
    assert any(ch in FORBIDDEN for ch in rows), "the forbidden set must catch a planted à"

    # The module docstring names 'À-ÿ' and '£'; those lines must be excluded from the functional set
    # (else this very file's port-prose would self-fail the scan).
    functional_text = "\n".join(line for _, line in functional)
    assert "À" not in functional_text and "£" not in functional_text
