"""CLI-3 — app/provider command classes surface in the CLI. The full appear-in-`--help` + run path
is exercised by tools/e2e_smoke.sh (consumer path); here we unit-test the name derivation + the
CLI-4 argument()/option() accessors (the kernel stashes the parsed context at dispatch)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from arvel.console import Command
from arvel.console.kernel import command_name, run_command_class
from arvel.kernel import Application, set_application


class ReportSend:
    signature = "report:send {user}"


class Plain:
    signature = ""


class CleanupOldRecords:
    pass


def test_command_name_is_the_first_signature_token() -> None:
    assert command_name(ReportSend) == "report:send"


def test_command_name_falls_back_to_snake_cased_class() -> None:
    assert command_name(Plain) == "plain"
    assert command_name(CleanupOldRecords) == "cleanup_old_records"


@pytest.fixture
def app() -> Iterator[Application]:
    application = Application()
    set_application(application)
    yield application
    set_application(None)


def test_argument_and_option_resolve_the_dispatched_values(app: Application) -> None:
    seen: dict[str, object] = {}

    class Notify(Command):
        signature = "notify {user} {--force}"

        async def handle(self) -> None:
            seen["user"] = self.argument("user")
            seen["force"] = self.option("force")

    run_command_class(Notify, user="Ada", force=True)
    assert seen == {"user": "Ada", "force": True}


def test_argument_and_option_default_to_none_when_unset(app: Application) -> None:
    seen: dict[str, object] = {}

    class Notify(Command):
        signature = "notify {user} {--force}"

        async def handle(self) -> None:
            seen["force"] = self.option("force")
            seen["missing"] = self.argument("nope")

    run_command_class(Notify, user="Ada")
    assert seen == {"force": None, "missing": None}


# -- Command.trap (E16) -------------------------------------------------------------------


def test_trap_fires_mid_run_and_the_command_exits_cleanly(app: Application) -> None:
    """A command registering a SIGTERM trap: delivering the signal mid-run invokes the handler,
    and the command still exits cleanly (no crash, no leaked traceback)."""
    import asyncio
    import os
    import signal

    seen: dict[str, object] = {}

    class Watcher(Command):
        async def handle(self) -> None:
            flag = asyncio.Event()
            self.trap(signal.SIGTERM, flag.set)
            os.kill(os.getpid(), signal.SIGTERM)
            await asyncio.wait_for(flag.wait(), timeout=2)
            seen["ran"] = True

    run_command_class(Watcher)  # raises on any exception/timeout — a clean run is the assertion
    assert seen == {"ran": True}


def test_trap_is_removed_to_default_after_the_command_exits(app: Application) -> None:
    """After the command returns, the loop no longer holds its handler — the OS-level signal
    disposition is back to default, not leaked past this run."""
    import signal

    class Watcher(Command):
        async def handle(self) -> None:
            self.trap(signal.SIGTERM, lambda: None)

    run_command_class(Watcher)
    assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL


def test_no_trap_command_behaves_exactly_as_today(app: Application) -> None:
    seen: dict[str, object] = {}

    class Plain(Command):
        async def handle(self) -> None:
            seen["ran"] = True

    run_command_class(Plain)
    assert seen == {"ran": True}


def test_close_traps_is_a_no_op_when_no_trap_was_registered() -> None:
    """A command that never calls `trap()` never opens an ExitStack — closing is a no-op."""
    command = Command()
    command._close_traps()  # must not raise
    assert command._trap_scope is None
