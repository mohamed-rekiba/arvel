"""Closure console commands — Laravel's ``routes/console.php`` ``Artisan::command``.

Define ad-hoc commands in ``routes/console.py`` with ``Console.command("greet {name}", handler)``; the
console kernel discovers them into ``--help`` and dispatches them through the booted app, with container
dependency-injection on the handler (CLI tokens are passed by name; the rest is autowired).

Signature tokens: ``{arg}`` (required positional), ``{arg?}`` (optional positional), ``{--flag}`` (boolean
option). Kept dependency-light at module level (no typer) so ``from arvel import Console`` stays cheap —
the typer command is built lazily at CLI time (see ``console.lazy``).
"""

from __future__ import annotations

import re
from typing import Any

_TOKEN = re.compile(r"\{(--)?(\w+)(\?)?\}")


class ClosureCommand:
    """A name + Laravel-style signature + handler, registered on the app for the console kernel."""

    def __init__(self, signature: str, handler: Any) -> None:
        self.signature = signature.strip()
        self.handler = handler
        self.name = self.signature.split()[0]

    def arguments(self) -> list[tuple[str, bool, bool]]:
        """Parse the signature into ``(name, is_option, optional)`` tuples — ``{x}`` → required arg,
        ``{x?}`` → optional arg, ``{--flag}`` → boolean option (always optional)."""
        out: list[tuple[str, bool, bool]] = []
        for match in _TOKEN.finditer(self.signature):
            is_option = match.group(1) == "--"
            optional = is_option or match.group(3) == "?"
            out.append((match.group(2), is_option, optional))
        return out


class _ConsoleRegistrar:
    """``from arvel import Console`` — registers closure commands onto the current application
    (Laravel ``Artisan::command``). Used from ``routes/console.py``."""

    def command(self, signature: str, handler: Any) -> ClosureCommand:
        from arvel.kernel import app

        command = ClosureCommand(signature, handler)
        app().console_commands[command.name] = command
        return command


Console = _ConsoleRegistrar()


def run_closure_command(name: str, cli_args: dict[str, Any]) -> None:
    """Dispatch a closure command through the booted app: look it up in ``console_commands`` (the
    console kernel loads ``routes/console.py`` during boot) and call its handler with DI + the parsed
    CLI tokens passed by name."""
    from arvel.console.kernel import run_app_command

    async def handler(app: Any) -> None:
        import inspect

        command = app.console_commands.get(name)
        if (
            command is None
        ):  # pragma: no cover - defensive (discovery + dispatch use the same loader)
            import typer

            typer.echo(f"command {name!r} is not defined in routes/console.py")
            raise typer.Exit(1)
        result = app.call(command.handler, **cli_args)
        if inspect.isawaitable(result):
            await result

    run_app_command(handler)
