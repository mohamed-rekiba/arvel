"""Show framework version and environment details."""

from __future__ import annotations

import platform
import sys
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from arvel.cli.plugins._base import CliPlugin

_app = typer.Typer(name="about", help="Show framework information.", invoke_without_command=True)


def _get_version() -> str:
    try:
        from importlib.metadata import version

        return version("arvel")
    except Exception:
        return "unknown"


@_app.callback(invoke_without_command=True)
def about(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Print Arvel version, Python version, and platform info."""
    import json

    info = {
        "framework": "Arvel",
        "version": _get_version(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "executable": sys.executable,
    }

    if json_output:
        typer.echo(json.dumps(info, indent=2))
        return

    typer.echo("Arvel Framework")
    typer.echo(f"  Version:    {info['version']}")
    typer.echo(f"  Python:     {info['python']}")
    typer.echo(f"  Platform:   {info['platform']}")
    typer.echo(f"  Executable: {info['executable']}")


class _Plugin:
    name = "about"
    help = "Show framework information."

    def register(self, app: typer.Typer) -> None:
        app.add_typer(_app, name=self.name)


plugin: CliPlugin = _Plugin()  # type: ignore[assignment]
