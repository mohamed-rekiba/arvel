"""CLI-3 — app/provider command classes surface in the CLI. The full appear-in-`--help` + run path
is exercised by tools/e2e_smoke.sh (consumer path); here we unit-test the name derivation."""

from __future__ import annotations

from arvel.console.kernel import command_name


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
