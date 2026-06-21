"""M0 scaffold smoke test.

Proves the package imports cleanly, the step modules are present as stubs, and the
CLI shell is wired — without claiming any step is actually ported yet. As steps land
in later milestones, their stub assertions migrate into real golden/unit tests.
"""

from __future__ import annotations

import importlib

import pytest

import engine
from engine import cli


def test_package_imports_and_has_version():
    assert engine.__version__
    assert isinstance(engine.STEPS, tuple)
    # The ordered build subset through typeset (plus manual-only refine).
    assert engine.STEPS[0] == "download"
    assert "validate" in engine.STEPS
    assert engine.STEPS[-1] == "typeset"


@pytest.mark.parametrize("step", engine.STEPS)
def test_every_step_module_imports_with_a_stub_run(step):
    module = importlib.import_module(f"engine.steps.{step}")
    assert hasattr(module, "run"), f"engine.steps.{step} must expose run()"
    with pytest.raises(NotImplementedError):
        module.run()


def test_cli_parser_builds_and_lists_steps():
    parser = cli.build_parser()
    ns = parser.parse_args(["--step", "validate", "--book", "per_la_liberta"])
    assert ns.step == "validate"
    assert ns.book == "per_la_liberta"


def test_cli_main_with_no_step_is_a_noop_error():
    # No --step and no --list-books → usage error exit code, not a crash.
    assert cli.main([]) == 1
