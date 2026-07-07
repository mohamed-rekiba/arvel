"""``auth:clear-resets`` — sweep expired password-reset tokens.

``PasswordBroker`` already deletes a reset row on every terminal outcome (a successful reset, or an
expired token hit on ``reset()``) — but a row that's never redeemed just sits past its TTL until then.
This command sweeps those stragglers on a schedule (cron / ``Schedule``), so the table doesn't grow
unbounded with dead rows. Same table + the same TTL constant ``PasswordBroker`` uses — no new state,
no change to ``arvel.auth.password_reset``.
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


async def _clear_expired_resets(_app: Any) -> None:
    from arvel.auth.password_reset import DEFAULT_TTL_SECONDS, PasswordResetToken
    from arvel.dates import Date

    cutoff = Date.now().subtract(seconds=DEFAULT_TTL_SECONDS)
    result = await PasswordResetToken.where("created_at", "<", cutoff).delete()
    typer.echo(f"deleted {result.rowcount} expired password reset token(s)")
