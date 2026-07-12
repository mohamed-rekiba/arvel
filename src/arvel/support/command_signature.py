"""Console command-signature grammar — the pure parser, shared across the layer line.

Lives in ``support`` (below both ``console`` and ``testing`` in the module DAG) so the console
dispatcher AND the test console-runner parse signatures with the *same* grammar, instead of the
test harness keeping a drift-prone copy of it.

Grammar: ``{arg}`` required positional · ``{arg?}`` optional positional · ``{arg=default}``
positional with a default · ``{arg*}`` variadic positional (a list) · ``{--flag}`` boolean option ·
``{--opt=}`` value option · ``{--opt=*}`` multi-value option · ``{--Q|queue}`` a shortcut
(``-Q``/``--queue``), optionally combined with ``=``/``=*``. Dependency-light on purpose (only
stdlib), so importing it never pulls in typer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

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
    """Parse a console signature into typed tokens (module docstring has the grammar). The leading
    command name (``"report:send {user}"`` → ``report:send``) isn't a ``{...}`` token, so it's
    naturally skipped."""
    return [
        _parse_option(raw[2:]) if raw.startswith("--") else _parse_argument(raw)
        for raw in _TOKEN.findall(signature)
    ]


def validate_positional_order(tokens: list[SignatureArg], command: str) -> None:
    """Reject a required positional after an optional/defaulted/variadic one — the one signature
    shape the CLI cannot dispatch. Shared by closure registration (raise at ``Console.command``
    time, per the docs) and the lazy typer builder (class commands), so both surfaces enforce
    the same rule with the same message."""
    seen_optional = False
    for token in tokens:
        if token.is_option:
            continue
        if token.optional or token.default is not None or token.variadic:
            seen_optional = True
        elif seen_optional:
            message = (
                f"command {command!r}: required argument {{{token.name}}} cannot "
                f"follow an optional one (an optional positional must come last)"
            )
            raise ValueError(message)


__all__ = ["SignatureArg", "parse_signature", "validate_positional_order"]
