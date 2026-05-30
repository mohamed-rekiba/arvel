"""``make:command`` — generate an Arvel console command stub.

The generated class subclasses :class:`arvel.console.Command` and
implements :meth:`Command.handle`, the default entry point for
zero-argument commands. For commands that need typed CLI flags, override
:meth:`Command.register` and drive Typer directly (see
``docs/site/docs/artisan.md`` § "Writing your own commands").

Set ``needs_application = True`` to opt into framework DI — ``self.app``
is then the booted ``Application`` and you can resolve services from
its container.
"""

from __future__ import annotations

from typing import ClassVar

from arvel.console.commands._base_make import BaseMakeCommand
from arvel.support.str import Str


def _to_cli_name(name: str) -> str:
    return Str.snake(name).replace("_", ":").removesuffix(":command")


_TEMPLATE = '''"""{title} — console command."""

from __future__ import annotations

from typing import ClassVar

from arvel.console import Command, Context


class {title}(Command):
    name: ClassVar[str] = "{cli_name}"
    help: ClassVar[str] = "{help_text}"
    needs_application: ClassVar[bool] = False

    def handle(self, ctx: Context) -> int:
        ctx.info("Running {cli_name}...")
        return 0
'''


class MakeCommandCommand(BaseMakeCommand):
    name: ClassVar[str] = "make:command"
    help: ClassVar[str] = "Generate an Arvel console command"
    _target_subdir: ClassVar[str] = "app/console/commands"

    def _render(self, name: str) -> str:
        cli_name = _to_cli_name(name)
        return _TEMPLATE.format(
            title=Str.pascal(name),
            cli_name=cli_name,
            help_text=f"Run the {cli_name} command",
        )
