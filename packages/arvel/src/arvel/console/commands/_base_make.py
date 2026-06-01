"""Shared base for all make:* file generators."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, ClassVar

import typer

from arvel.console import Command, Context
from arvel.console._t import Argument as _Argument
from arvel.console._t import Option as _Option
from arvel.support.str import Str

_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def validate_name(name: str) -> str | None:
    """Return None when ``name`` is safe; otherwise an error message.

    The allowlist rejects path traversal, shell metacharacters, and any name
    that doesn't start with a letter — same rule as ``make:migration``.
    Public so sibling ``make:*`` commands can reuse the check when they
    accept secondary identifier flags (e.g. ``make:controller --model=Post``).
    """
    if not name:
        return "Name must not be empty."
    if not _NAME_PATTERN.match(name):
        return (
            "Name must match ^[A-Za-z][A-Za-z0-9_]*$ "
            "(letters, digits, underscore; must start with a letter)."
        )
    return None


class BaseMakeCommand(Command):
    """Create a file at a canonical path from a class-name template.

    Subclasses configure ``_target_subdir`` (directory) and ``_extension``
    (defaults to ``.py``). Subclasses MUST override :meth:`_render` to produce
    a framework-aware stub.
    """

    _target_subdir: ClassVar[str]
    _extension: ClassVar[str] = ".py"

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback(
            name: Annotated[str, _Argument(help="Class name")],
            *,
            force: Annotated[bool, _Option("--force", help="Overwrite existing")] = False,
        ) -> None:
            code = cmd_self._generate(name, force=force)
            if code != 0:
                raise typer.Exit(code)

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError

    def _generate(self, name: str, *, force: bool = False) -> int:
        error = validate_name(name)
        if error is not None:
            typer.echo(f"arvel: {error}", err=True)
            return 2
        target = Path(self._target_subdir) / f"{Str.snake(name)}{self._extension}"
        if target.exists() and not force:
            typer.echo(f"arvel: {target} already exists. Pass --force to overwrite.", err=True)
            return 1
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self._render(name))
        typer.echo(f"Created: {target}")
        return 0

    def _render(self, name: str) -> str:
        """Render the stub content.

        Default fallback — every subclass should override this with a real,
        framework-aware template (see project docs).
        """
        return (
            f'"""{name}."""\n'
            "\n"
            "from __future__ import annotations\n"
            "\n"
            "\n"
            f"class {name}:\n"
            f'    """{name} class."""\n'
        )
