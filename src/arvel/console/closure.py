"""Closure console commands — Laravel's ``routes/console.php`` ``Artisan::command``.

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

import re
from dataclasses import dataclass
from typing import Any

#: One `{...}` signature token, argument or option (leading `--` already stripped by the caller).
_TOKEN = re.compile(r"\{([^{}]+)\}")


@dataclass(frozen=True, slots=True)
class SignatureArg:
    """One parsed signature token — see the module docstring for the grammar."""

    name: str
    is_option: bool = False
    optional: bool = False
    default: str | None = None
    variadic: bool = False
    #: options only: ``{--opt=}``/``{--opt=*}`` (a value) vs a bare ``{--flag}`` (boolean).
    takes_value: bool = False
    shortcut: str | None = None


def _parse_argument(body: str) -> SignatureArg:
    if "=" in body:
        name, default = body.split("=", 1)
        return SignatureArg(name=name, optional=True, default=default)
    if body.endswith("*"):
        return SignatureArg(name=body[:-1], optional=True, variadic=True)
    if body.endswith("?"):
        return SignatureArg(name=body[:-1], optional=True)
    return SignatureArg(name=body)


def _parse_option(body: str) -> SignatureArg:
    shortcut = None
    if "|" in body:
        shortcut, body = body.split("|", 1)
    if body.endswith("=*"):
        return SignatureArg(
            name=body[:-2],
            is_option=True,
            optional=True,
            variadic=True,
            takes_value=True,
            shortcut=shortcut,
        )
    if body.endswith("="):
        return SignatureArg(
            name=body[:-1], is_option=True, optional=True, takes_value=True, shortcut=shortcut
        )
    return SignatureArg(name=body, is_option=True, optional=True, shortcut=shortcut)


def parse_signature(signature: str) -> list[SignatureArg]:
    """Parse a Laravel-style console signature into typed tokens (module docstring has the grammar).
    The leading command name (``"report:send {user}"`` → ``report:send``) isn't a ``{...}`` token, so
    it's naturally skipped."""
    return [
        _parse_option(raw[2:]) if raw.startswith("--") else _parse_argument(raw)
        for raw in _TOKEN.findall(signature)
    ]


class ClosureCommand:
    """A name + Laravel-style signature + handler, registered on the app for the console kernel."""

    def __init__(self, signature: str, handler: Any) -> None:
        self.signature = signature.strip()
        self.handler = handler
        self.name = self.signature.split()[0]

    def tokens(self) -> list[SignatureArg]:
        """The full typed signature spec — see :func:`parse_signature`."""
        return parse_signature(self.signature)

    def arguments(self) -> list[tuple[str, bool, bool]]:
        """Back-compat projection: ``(name, is_option, optional)``. See :meth:`tokens` for the full
        spec (defaults, variadics, value/multi options, shortcuts)."""
        return [(t.name, t.is_option, t.optional) for t in self.tokens()]


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
