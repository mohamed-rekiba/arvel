"""``key:generate`` — produce a new base64-encoded ``APP_KEY``.

Mirrors Laravel's ``artisan key:generate``. By default, writes/replaces the
``APP_KEY=`` line in the project's ``.env`` file. ``--show`` prints the key to
stdout instead. Refuses to overwrite an existing populated key without
``--force`` so a careless invocation can't destroy production secrets.
"""

from __future__ import annotations

import base64
import re
import secrets
from pathlib import Path
from typing import Annotated, ClassVar

import typer

from arvel.console import Command, Context
from arvel.console._t import Option as _Option

_KEY_BYTES = 32
_APP_KEY_RE = re.compile(r"^APP_KEY=(.*)$", flags=re.MULTILINE)


def _generate_key() -> str:
    raw = secrets.token_bytes(_KEY_BYTES)
    encoded = base64.b64encode(raw).decode("ascii")
    return f"base64:{encoded}"


class KeyGenerateCommand(Command):
    name: ClassVar[str] = "key:generate"
    help: ClassVar[str] = "Generate a new APP_KEY (base64) and write it to .env"

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback(
            *,
            show: Annotated[
                bool, _Option("--show", help="Print the key instead of writing .env")
            ] = False,
            force: Annotated[
                bool,
                _Option("--force", help="Overwrite a populated APP_KEY without prompting"),
            ] = False,
        ) -> None:
            code = cmd_self.generate(show=show, force=force)
            if code != 0:
                raise typer.Exit(code)

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError

    def generate(self, *, show: bool, force: bool) -> int:
        key = _generate_key()
        if show:
            typer.echo(key)
            return 0

        env = Path(".env")
        if not env.is_file():
            typer.echo(
                "ERROR: .env not found in the current directory. "
                "Run from your project root, or use --show to print the key.",
                err=True,
            )
            return 2

        content = env.read_text()
        match = _APP_KEY_RE.search(content)
        if match is not None and match.group(1).strip() and not force:
            typer.echo(
                "ERROR: APP_KEY is already set. Pass --force to overwrite.",
                err=True,
            )
            return 2

        new_line = f"APP_KEY={key}"
        if match is not None:
            new_content = _APP_KEY_RE.sub(new_line, content, count=1)
        else:
            sep = "" if content.endswith("\n") or content == "" else "\n"
            new_content = f"{content}{sep}{new_line}\n"
        env.write_text(new_content)
        typer.echo(f"APP_KEY set in {env}")
        return 0


__all__ = ["KeyGenerateCommand"]
