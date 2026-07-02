"""Console — openapi:export writes the compiled app's OpenAPI document (the codegen seam)."""

from __future__ import annotations

import json
from typing import Any

from typer.testing import CliRunner

from arvel.console import build_cli

runner = CliRunner()


def test_openapi_export_writes_the_document(tmp_path: Any) -> None:
    from arvel.kernel import Application, set_application
    from arvel.routing.provider import _build_served_kernel

    app = Application()
    app.instance("http.kernel_builder", _build_served_kernel)
    set_application(app)
    target = tmp_path / "openapi.json"
    try:
        result = runner.invoke(build_cli(), ["openapi:export", str(target)])
        assert result.exit_code == 0, result.output
        spec = json.loads(target.read_text())
        assert spec["openapi"].startswith("3.")
        assert "paths" in spec and "components" in spec
    finally:
        set_application(None)
