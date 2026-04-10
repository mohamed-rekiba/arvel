"""About command — display framework and environment information."""

from __future__ import annotations

import platform
import sys

import typer

about_app = typer.Typer(
    name="about", help="Show framework information.", invoke_without_command=True
)


def _get_version() -> str:
    try:
        from importlib.metadata import version

        return version("arvel")
    except Exception:
        return "unknown"


@about_app.callback(invoke_without_command=True)
def about(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Display Arvel framework and environment details."""
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
