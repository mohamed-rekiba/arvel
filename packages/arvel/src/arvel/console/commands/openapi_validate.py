"""openapi:validate — validate the application's OpenAPI spec."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, ClassVar

import typer

from arvel.console import Command, Context
from arvel.console._t import Option as _Option


class OpenApiValidateCommand(Command):
    """Validate the application's OpenAPI specification."""

    name: ClassVar[str] = "openapi:validate"
    help: ClassVar[str] = "Validate the OpenAPI spec against the OpenAPI 3.x schema."
    needs_application: ClassVar[bool] = True

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback(
            spec_path: Annotated[
                str | None,
                _Option("--spec", help="Path to an existing spec file to validate."),
            ] = None,
        ) -> None:
            # Delay import so ImportError is catchable at callback time.
            if "openapi_spec_validator" not in sys.modules:
                try:
                    import openapi_spec_validator  # noqa: F401, PLC0415  # pyright: ignore[reportUnusedImport]
                except ImportError as exc:
                    typer.echo(
                        "arvel: openapi-spec-validator is required for this command.\n"
                        "Install it: pip install 'arvel[openapi]'",
                        err=True,
                    )
                    raise typer.Exit(code=2) from exc

            validate = sys.modules["openapi_spec_validator"].validate

            if spec_path is not None:
                raw = Path(spec_path).read_text(encoding="utf-8")
                # Try YAML first, fall back to JSON.
                try:
                    import yaml  # noqa: PLC0415

                    spec: dict[str, object] = yaml.safe_load(raw)
                except ImportError:
                    spec = json.loads(raw)
            else:
                if cmd_self.app is None:
                    typer.echo("arvel: openapi:validate needs a framework Application.", err=True)
                    raise typer.Exit(code=2)
                spec = cmd_self.app.into_asgi().openapi()

            try:
                validate(spec)
            except Exception as exc:
                typer.echo(f"arvel: OpenAPI validation failed:\n  {exc}", err=True)
                raise typer.Exit(code=1) from exc

            typer.echo("OpenAPI spec is valid.")

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError


__all__ = ["OpenApiValidateCommand"]
