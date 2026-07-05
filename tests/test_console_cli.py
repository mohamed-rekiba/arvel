"""The CLI command tree uses colon names (`make:model`, `db:seed`, …) — both as the
invokable name AND as what `--help` displays. Regression guard: the manifest key must win over the
name Typer derives from the handler function (`make-model`), and `shell`/`tinker` must be distinct."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from arvel.console import build_cli

runner = CliRunner()


@pytest.mark.parametrize(
    "name",
    [
        "make:model",
        "make:controller",
        "make:migration",
        "db:seed",
        "migrate:rollback",
        "route:list",
    ],
)
def test_commands_resolve_by_their_colon_name(name: str) -> None:
    result = runner.invoke(build_cli(), [name, "--help"])
    assert result.exit_code == 0
    assert name in result.output  # the usage line shows the colon name


@pytest.mark.parametrize("name", ["make-model", "db-seed", "route-list"])
def test_hyphenated_forms_are_not_commands(name: str) -> None:
    result = runner.invoke(build_cli(), [name, "--help"])
    assert result.exit_code != 0


def test_shell_and_tinker_are_distinct() -> None:
    shell = runner.invoke(build_cli(), ["shell", "--help"])
    tinker = runner.invoke(build_cli(), ["tinker", "--help"])
    assert shell.exit_code == 0 and "shell" in shell.output
    assert tinker.exit_code == 0 and "tinker" in tinker.output
