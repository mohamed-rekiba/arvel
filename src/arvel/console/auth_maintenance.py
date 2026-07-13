"""``auth:clear-resets`` — sweep expired password-reset tokens.

The broker already deletes a reset row on every terminal outcome, but a row that's
never redeemed sits past its TTL until then. This command sweeps those stragglers on
a schedule so the table doesn't grow unbounded. The sweep itself lives in the auth
layer and is resolved from the container ("auth.reset_sweeper", bound by the auth
provider) — the console never imports the heavy auth/database stack (G2).
"""

from __future__ import annotations

from typing import Any

import typer

auth_maintenance_app = typer.Typer()


@auth_maintenance_app.command()
def auth_clear_resets() -> None:
    """Delete expired password-reset tokens."""
    from arvel.console.kernel import run_app_command

    run_app_command(_clear_expired_resets)


async def _clear_expired_resets(app: Any) -> None:
    if not app.bound("auth.reset_sweeper"):
        typer.echo("auth provider not registered; nothing to sweep")
        raise typer.Exit(1)
    sweeper = app.make("auth.reset_sweeper")
    deleted = await sweeper()
    typer.echo(f"deleted {deleted} expired password reset token(s)")
