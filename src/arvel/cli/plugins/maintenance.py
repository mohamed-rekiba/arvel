"""Maintenance mode — down writes a signal file, up removes it."""

from __future__ import annotations

import hashlib
import ipaddress
import json
from pathlib import Path
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from arvel.cli.plugins._base import CliPlugin


def _maintenance_path() -> Path:
    return Path.cwd() / "bootstrap" / "maintenance.json"


def down(
    secret: str | None = typer.Option(None, "--secret", "-s", help="Bypass secret token."),
    allow: list[str] | None = typer.Option(  # noqa: B008
        None, "--allow", "-a", help="Allowed IP/CIDR (repeatable)."
    ),
    retry: int | None = typer.Option(None, "--retry", "-r", help="Retry-After seconds."),
) -> None:
    """Put the application into maintenance mode."""
    allowed_ips: list[str] = []
    if allow:
        for cidr in allow:
            try:
                ipaddress.ip_network(cidr, strict=False)
            except ValueError:
                typer.echo(f"Error: invalid IP/CIDR: {cidr}")
                raise typer.Exit(code=1) from None
            allowed_ips.append(cidr)

    secret_hash: str | None = None
    if secret:
        digest = hashlib.sha256(secret.encode()).hexdigest()
        secret_hash = f"sha256:{digest}"

    data = {
        "secret_hash": secret_hash,
        "allowed_ips": allowed_ips,
        "retry_after": retry,
    }

    maint_file = _maintenance_path()
    maint_file.parent.mkdir(parents=True, exist_ok=True)
    maint_file.write_text(json.dumps(data, indent=2))

    typer.echo("Application is now in maintenance mode.")


def up() -> None:
    """Bring the application out of maintenance mode."""
    maint_file = _maintenance_path()
    if maint_file.exists():
        maint_file.unlink()
        typer.echo("Application is now live.")
    else:
        typer.echo("Application is already live.")


class _Plugin:
    name = "maintenance"
    help = "Maintenance mode commands."

    def register(self, app: typer.Typer) -> None:
        app.command(name="down")(down)
        app.command(name="up")(up)


plugin: CliPlugin = _Plugin()  # type: ignore[assignment]
