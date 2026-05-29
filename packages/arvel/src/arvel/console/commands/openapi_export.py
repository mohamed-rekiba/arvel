"""openapi:export — dump the application's OpenAPI spec to a file or stdout."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, ClassVar, Literal

import typer

from arvel.console import Command, Context
from arvel.console._t import Option as _Option


def _safe_output_path(raw: str, project_root: Path) -> Path:
    """Resolve *raw* relative to *project_root* and reject path traversal."""
    resolved = (project_root / raw).resolve()
    try:
        resolved.relative_to(project_root.resolve())
    except ValueError as exc:
        raise typer.BadParameter(f"--output path escapes the project root: {raw!r}") from exc
    return resolved


class OpenApiExportCommand(Command):
    """Export the application's OpenAPI specification to a file."""

    name: ClassVar[str] = "openapi:export"
    help: ClassVar[str] = "Export the OpenAPI spec to a file (YAML or JSON)."
    needs_application: ClassVar[bool] = True

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback(
            output: Annotated[
                str,
                _Option("--output", "-o", help="Output path (relative to project root)."),
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

            if stdout:
                typer.echo(text, nl=False)
                return

            base: Path = (
                cmd_self.app.base_path()
                if callable(getattr(cmd_self.app, "base_path", None))
                else Path.cwd()
            )
            out_path = _safe_output_path(output, base)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(text, encoding="utf-8")
            typer.echo(f"OpenAPI spec written to {out_path}")

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError


__all__ = ["OpenApiExportCommand"]
