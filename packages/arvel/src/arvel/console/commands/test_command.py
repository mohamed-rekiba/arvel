"""test — forward to pytest in-process via pytest.main()."""

from __future__ import annotations

import importlib
from typing import Annotated, ClassVar, Protocol, SupportsInt, cast

import typer

from arvel.console import Command, Context
from arvel.console._t import Argument as _Argument


class _PytestModule(Protocol):
    def main(self, args: list[str]) -> SupportsInt: ...


def _load_pytest() -> _PytestModule:
    try:
        module = importlib.import_module("pytest")
    except ModuleNotFoundError as exc:
        if exc.name != "pytest":
            raise
        message = "pytest is not installed; install dev dependencies to use arvel test."
        raise RuntimeError(message) from exc
    return cast("_PytestModule", module)


class TestCommand(Command):
    name: ClassVar[str] = "test"
    help: ClassVar[str] = "Run pytest against the application"

    def register(self, app: typer.Typer) -> None:
        def _callback(
            args: Annotated[list[str] | None, _Argument(help="Pytest arguments")] = None,
        ) -> None:
            try:
                pytest = _load_pytest()
            except RuntimeError as exc:
                typer.echo(str(exc), err=True)
                raise typer.Exit(code=2) from exc
            code = pytest.main(list(args or []))
            if code != 0:
                raise typer.Exit(code=int(code))

        app.command(
            name=self.name,
            help=self.help,
            context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
        )(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError
