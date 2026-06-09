"""``make:command`` — generate an Arvel console command stub.

The generated class subclasses :class:`arvel.console.Command` and
implements :meth:`Command.handle`, the default entry point for
zero-argument commands. For commands that need typed CLI flags, override
:meth:`Command.register` and drive Typer directly (see
``docs/site/artisan.md`` § "Writing your own commands").

Declare ``requires`` to opt into framework DI — the entrypoint then boots
the listed subsystems and binds the resulting ``Application`` to
``self.app`` so you can resolve services from its container.
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

# Declare framework subsystems this command needs. The entrypoint then boots
# only those providers and binds the application to self.app. Leave empty for
# pure-CLI commands that don't touch the framework.
# from arvel.console._subsystem import CliSubsystem


class {title}(Command):
    name: ClassVar[str] = "{cli_name}"
    help: ClassVar[str] = "{help_text}"
    # requires: ClassVar[frozenset[CliSubsystem]] = frozenset({{CliSubsystem.CONFIG}})

    def handle(self, ctx: Context) -> int:
        ctx.info("Running {cli_name}...")
        return 0
'''


class MakeCommandCommand(BaseMakeCommand):
    name: ClassVar[str] = "make:command"
    help: ClassVar[str] = "Generate an Arvel console command"
    _target_subdir: ClassVar[str] = "app/console/commands"
    _suffix: ClassVar[str] = "Command"

    def _render(self, name: str) -> str:
        cli_name = _to_cli_name(name)
        return _TEMPLATE.format(
            title=Str.pascal(name),
            cli_name=cli_name,
            help_text=f"Run the {cli_name} command",
        )
