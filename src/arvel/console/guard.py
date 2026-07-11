"""Destructive-command guard — the shared safety gate every table-dropping / data-wiping console
command routes through, so none of them re-implements (or forgets) the check.

Policy: ``--force`` bypasses; otherwise **refuse in production**, **prompt on an interactive
terminal**, and **require --force when there is no TTY** (CI / a piped stdin) — so a scripted run
can never silently wipe a database and a production run needs an explicit override.
"""

from __future__ import annotations

import sys
from typing import Any

import typer


def confirm_destructive(app: Any, *, force: bool, action: str) -> None:
    """Gate a destructive database command. Returns normally when it is safe to proceed; otherwise
    raises ``typer.Exit(1)``. ``action`` is a short verb phrase (e.g. ``"drop all tables"``) used in
    the refusal / prompt text."""
    if force:
        return

    env = str(app.config("app.env", "local") or "local").strip().lower()
    if env in {"production", "prod"}:
        typer.echo(
            f"Refusing to {action} in production — this is destructive and irreversible. "
            "Re-run with --force if you are certain.",
            err=True,
        )
        raise typer.Exit(1)

    if not sys.stdin.isatty():
        typer.echo(
            f"'{action}' is destructive and needs confirmation, but there is no interactive "
            "terminal. Re-run with --force to proceed non-interactively.",
            err=True,
        )
        raise typer.Exit(1)

    if not typer.confirm(f"This will {action}. Continue?"):
        typer.echo("Aborted.")
        raise typer.Exit(1)
