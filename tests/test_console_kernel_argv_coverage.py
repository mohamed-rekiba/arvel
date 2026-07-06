"""arvel.console.kernel — the CLI-shaping helper ``_cli_argv`` (dict/list -> argv tokens) and
the ``Cli.call`` dispatch guards for app-registered commands."""

from __future__ import annotations

import pytest

from arvel.console.kernel import (
    Cli,
    _cli_argv,  # pyright: ignore[reportPrivateUsage]
)
from arvel.kernel import set_application
from arvel.kernel.application import Application


def test_cli_argv_none_and_list_passthrough() -> None:
    assert _cli_argv(None) == []
    assert _cli_argv(["a", "b"]) == ["a", "b"]
    assert _cli_argv([1, 2]) == ["1", "2"]  # coerced to str


def test_cli_argv_dict_flag_option_and_positional_forms() -> None:
    argv = _cli_argv(
        {
            "--force": True,  # flag present
            "--dry": False,  # flag absent -> skipped
            "--skip": None,  # also skipped
            "--tag": ["a", "b"],  # repeated option
            "--name": "web",  # single option
            "count": 3,  # positional
            "ids": [1, 2],  # variadic positional
        }
    )
    assert "--force" in argv
    assert "--dry" not in argv and "--skip" not in argv
    assert argv.count("--tag") == 2
    assert "web" in argv
    assert "3" in argv
    assert "1" in argv and "2" in argv


def test_call_unknown_command_without_application_raises() -> None:
    set_application(None)
    with pytest.raises(RuntimeError, match="no active application"):
        Cli.call("definitely-not-a-command")


def test_call_app_command_rejects_a_list_of_args() -> None:
    app = Application()
    set_application(app)
    try:
        with pytest.raises(TypeError, match="takes a dict of args, not a list"):
            Cli.call("some-app-command", ["positional"])
    finally:
        set_application(None)
