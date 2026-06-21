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


def test_cli_resolves_real_book_then_hits_stub():
    # M1 wiring: a real --step run resolves PLL's manifest + profiles + plugin +
    # workspace (no crash), then surfaces the not-yet-ported step stub as exit 2.
    assert cli.main(["--step", "validate", "--book", "per_la_liberta"]) == 2


def test_cli_unknown_book_is_a_config_error():
    # A missing manifest is a clean ConfigError → exit 1, not a traceback.
    assert cli.main(["--step", "validate", "--book", "no_such_book"]) == 1


def test_registry_unknown_language_raises_clean_error():
    from engine.lang.registry import UnknownLanguageError, get_language_plugin

    with pytest.raises(UnknownLanguageError, match="no LanguagePlugin"):
        get_language_plugin("zz")


def test_cli_unknown_language_is_exit_1(monkeypatch):
    # A manifest whose language has no plugin resolves cleanly to exit 1, not a traceback.
    from engine.lang.registry import UnknownLanguageError

    def _raise(_lid):
        raise UnknownLanguageError("no plugin for test")

    monkeypatch.setattr(cli, "get_language_plugin", _raise)
    assert cli.main(["--step", "validate", "--book", "per_la_liberta"]) == 1
