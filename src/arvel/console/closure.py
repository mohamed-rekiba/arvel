"""Closure console commands — the ``routes/console.py closure-command surface``.

Define ad-hoc commands in ``routes/console.py`` with ``Console.command("greet {name}", handler)``; the
console kernel discovers them into ``--help`` and dispatches them through the booted app, with container
dependency-injection on the handler (CLI tokens are passed by name; the rest is autowired).

Signature grammar (shared with app/provider ``Command`` classes — see ``console.lazy``):
``{arg}`` required positional · ``{arg?}`` optional positional · ``{arg=default}`` positional with a
default · ``{arg*}`` variadic positional (a list) · ``{--flag}`` boolean option · ``{--opt=}`` value
option · ``{--opt=*}`` multi-value option · ``{--Q|queue}`` a shortcut (``-Q``/``--queue``), optionally
combined with ``=``/``=*``. Kept dependency-light at module level (no typer) so ``from arvel import
Console`` stays cheap — the typer command is built lazily at CLI time (see ``console.lazy``).
"""

from __future__ import annotations

from typing import Any

# The signature grammar moved to `support` (below the layer line) so the test console-runner shares
# this exact parser instead of copying it — re-exported here for console's existing call sites.
from arvel.support.command_signature import SignatureArg, parse_signature

__all__ = ["ClosureCommand", "Console", "SignatureArg", "parse_signature"]


class ClosureCommand:
    """A name + signature + handler, registered on the app for the console kernel."""

    def __init__(self, signature: str, handler: Any) -> None:
        self.signature = signature.strip()
        self.handler = handler
        self.name = self.signature.split()[0]

    def tokens(self) -> list[SignatureArg]:
        """The full typed signature spec — see:func:`parse_signature`."""
        return parse_signature(self.signature)

    def arguments(self) -> list[tuple[str, bool, bool]]:
        """Back-compat projection: ``(name, is_option, optional)``. See:meth:`tokens` for the full
        spec (defaults, variadics, value/multi options, shortcuts)."""
        return [(t.name, t.is_option, t.optional) for t in self.tokens()]


class _ConsoleRegistrar:
    """``from arvel import Console`` — registers closure commands onto the current application. Used from ``routes/console.py``."""

    def command(self, signature: str, handler: Any) -> ClosureCommand:
        from arvel.kernel import app

        command = ClosureCommand(signature, handler)
        app().registry("console.closure_commands", dict)[command.name] = command
        return command


Console = _ConsoleRegistrar()


def run_closure_command(name: str, cli_args: dict[str, Any]) -> None:
    """Dispatch a closure command through the booted app: look it up in the ``console.closure_commands`` registry (the
    console kernel loads ``routes/console.py`` during boot) and call its handler with DI + the parsed
    CLI tokens passed by name."""
    from arvel.console.kernel import run_app_command

    async def handler(app: Any) -> None:
        import inspect

        command = app.registry("console.closure_commands", dict).get(name)
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
