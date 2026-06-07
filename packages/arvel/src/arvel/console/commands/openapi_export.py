"""openapi:export — dump the application's OpenAPI spec to a file or stdout."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, ClassVar, Literal

import typer

from arvel.console import Command, Context
from arvel.console._subsystem import CliSubsystem
from arvel.console._t import Option as _Option


def _resolve_output_path(raw: str) -> Path:
    """Resolve ``--output`` against CWD; accept absolute paths verbatim.

    No project-root jail — callers writing into a sibling frontend
    (``--output ../frontend/openapi.yaml``) shouldn't have to fight the CLI.
    Use the OS for path safety.
    """
    candidate = Path(raw).expanduser()
    return candidate if candidate.is_absolute() else (Path.cwd() / candidate).resolve()


class OpenApiExportCommand(Command):
    """Export the application's OpenAPI specification to a file."""

    name: ClassVar[str] = "openapi:export"
    help: ClassVar[str] = "Export the OpenAPI spec to a file (YAML or JSON)."
    # HTTP for the Router/exception handler; USER_PROVIDERS for user-defined routes.
    requires: ClassVar[frozenset[CliSubsystem]] = frozenset(
        {CliSubsystem.HTTP, CliSubsystem.USER_PROVIDERS}
    )

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback(
            output: Annotated[
                str,
                _Option(
                    "--output",
                    "-o",
                    help=(
                        "Output path (resolved against CWD; absolute paths allowed; '-' = stdout)."
                    ),
                ),
            ] = "docs/api/openapi.yaml",
            fmt: Annotated[
                Literal["yaml", "json"],
                _Option("--format", "-f", help="Output format."),
            ] = "yaml",
            *,
            stdout: Annotated[
                bool,
                _Option("--stdout", help="Print to stdout instead of writing a file."),
            ] = False,
        ) -> None:
            if cmd_self.app is None:
                typer.echo("arvel: openapi:export needs a framework Application.", err=True)
                raise typer.Exit(code=2)

            asgi_app = cmd_self.app.into_asgi()
            spec: dict[str, object] = asgi_app.openapi()

            if fmt == "json":
                text = json.dumps(spec, indent=2)
            else:
                try:
                    import yaml  # noqa: PLC0415
                except ImportError as exc:
                    typer.echo(
                        "arvel: pyyaml is required for --format yaml. "
                        "Install it: pip install pyyaml",
                        err=True,
                    )
                    raise typer.Exit(code=2) from exc
                text = yaml.safe_dump(spec, sort_keys=False, allow_unicode=True)

            if stdout or output == "-":
                typer.echo(text, nl=False)
                return

            out_path = _resolve_output_path(output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(text, encoding="utf-8")
            # Status text goes to stderr so the file path is human-visible
            # without ever contaminating stdout (which a future `--stdout`
            # invocation streams the spec to).
            typer.echo(f"OpenAPI spec written to {out_path}", err=True)

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError


__all__ = ["OpenApiExportCommand"]
