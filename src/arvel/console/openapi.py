"""``openapi:export`` — write the app's OpenAPI document to a file (Laravel has no direct
equivalent; this is the codegen seam: client generators (orval, openapi-typescript, …) consume the
exported document in CI without booting a server)."""

from __future__ import annotations

from typing import Any

import typer

openapi_export_app = typer.Typer()


@openapi_export_app.command()
def openapi_export(
    path: str = typer.Argument("openapi.json", help="Where to write the document."),
) -> None:
    """Render the OpenAPI document from the compiled app (no server) and write it as JSON."""
    from arvel.console.kernel import run_app_command

    async def _handler(app: Any) -> None:
        import json
        from pathlib import Path

        kernel = app.make("http.kernel_builder")(app)
        Path(path).write_text(json.dumps(kernel.openapi(), indent=2) + "\n")
        typer.echo(f"OpenAPI document written to {path}")

    run_app_command(_handler)
