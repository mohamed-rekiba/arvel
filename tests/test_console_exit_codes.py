"""Command exit semantics: int returns become exit codes, fail() aborts with 1,
and a missing required argument prompts interactively / errors otherwise."""

from __future__ import annotations

import pytest

from arvel.console import Command, CommandFailed


class ExitCoded(Command):
    signature = "demo:exit"
    description = "returns a nonzero exit code"

    async def handle(self) -> int:
        return 2


class Failing(Command):
    signature = "demo:fail"
    description = "aborts via fail()"

    async def handle(self) -> None:
        self.fail("nope")


class NeedsName(Command):
    signature = "demo:hello {name}"
    description = "requires a name"

    async def handle(self) -> str:
        return str(self.argument("name"))


def test_fail_raises_command_failed() -> None:
    with pytest.raises(CommandFailed, match="nope"):
        Failing().fail("nope")


def test_missing_required_argument_errors_without_tty() -> None:
    cmd = NeedsName()
    with pytest.raises(CommandFailed, match="missing required argument: name"):
        cmd.bind_parsed({})  # test process: stdin is not a TTY


def test_missing_required_argument_prompts_on_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    class FakeTty:
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr(sys, "stdin", FakeTty())
    cmd = NeedsName()
    monkeypatch.setattr(cmd, "ask", lambda label, default=None: "ada")
    cmd.bind_parsed({})
    assert cmd.argument("name") == "ada"


def test_supplied_argument_never_prompts() -> None:
    cmd = NeedsName()
    cmd.bind_parsed({"name": "bob"})
    assert cmd.argument("name") == "bob"


async def test_int_return_becomes_exit_code() -> None:
    import typer

    from arvel.console.kernel import run_command_class
    from arvel.kernel.application import Application
    from arvel.kernel.globals import set_application

    app = Application()
    set_application(app)
    try:
        with pytest.raises(typer.Exit) as exc_info:
            run_command_class(ExitCoded)
        assert exc_info.value.exit_code == 2
    finally:
        set_application(None)
