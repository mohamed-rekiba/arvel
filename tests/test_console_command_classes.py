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
