"""Maintenance mode commands + middleware.

down creates marker file
down generates and prints a token when --secret omitted
up deletes marker (idempotent)
HTTP request without marker is served normally
HTTP with marker + no bypass returns 503
HTTP with ?bypass=<secret> sets cookie and passes through
HTTP with bypass cookie passes through
SR-023-001 token has ≥ 256 bits entropy
SR-023-002 bypass cookie is HttpOnly + SameSite=Lax
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

# RED: imports fail until Stage 3b
from arvel.console import Application, Command
from arvel.console.commands.maintenance import DownCommand, UpCommand
from arvel.maintenance import MaintenanceModeManager, MaintenanceModeMiddleware
from typer.testing import CliRunner

runner = CliRunner()


def _app(*cmds: Command) -> Application:
    return Application(commands=list(cmds))


# ─── — down creates marker ──────────────────────────────────────────


def test_down_creates_marker_file(tmp_path: Path) -> None:
    """down writes JSON marker at storage/framework/down."""
    app = _app(DownCommand())
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(app.typer_app, ["down", "--secret", "test-secret"])
        assert result.exit_code == 0, result.output
        marker = Path("storage/framework/down")
        assert marker.exists()
        data = json.loads(marker.read_text())
        assert data["secret"] == "test-secret"


# ─── — down without --secret generates a token ─────────────────────


def test_down_generates_token_when_secret_omitted(tmp_path: Path) -> None:
    """/ SR-023-001: token auto-generated with ≥ 256 bits entropy."""
    app = _app(DownCommand())
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(app.typer_app, ["down"])
        assert result.exit_code == 0
        marker = Path("storage/framework/down")
        data = json.loads(marker.read_text())
        # token_urlsafe(32) → 43+ chars
        assert len(data["secret"]) >= 43
        # token must appear on stdout so operators can capture it
        assert data["secret"] in result.output


def test_down_token_is_unique_per_invocation(tmp_path: Path) -> None:
    """SR-023-001: each invocation generates a fresh token."""
    app = _app(DownCommand(), UpCommand())
    with runner.isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(app.typer_app, ["down"])
        first = json.loads(Path("storage/framework/down").read_text())["secret"]
        runner.invoke(app.typer_app, ["up"])
        runner.invoke(app.typer_app, ["down"])
        second = json.loads(Path("storage/framework/down").read_text())["secret"]
        assert first != second


# ─── — up removes marker (idempotent) ────────────────────────────────


def test_up_removes_marker(tmp_path: Path) -> None:
    """up deletes the marker file."""
    app = _app(DownCommand(), UpCommand())
    with runner.isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(app.typer_app, ["down"])
        assert Path("storage/framework/down").exists()
        result = runner.invoke(app.typer_app, ["up"])
        assert result.exit_code == 0
        assert not Path("storage/framework/down").exists()


def test_up_is_idempotent_when_no_marker(tmp_path: Path) -> None:
    """up when no marker exists exits 0."""
    app = _app(UpCommand())
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(app.typer_app, ["up"])
        assert result.exit_code == 0


# ─── MaintenanceModeManager — direct API ─────────────────────────────────────


def test_manager_is_down_returns_false_when_no_marker(tmp_path: Path) -> None:
    """MaintenanceModeManager.is_down returns False when no marker exists."""
    marker_path = tmp_path / "down"
    manager = MaintenanceModeManager(marker_path=marker_path)
    assert manager.is_down() is False


def test_manager_down_writes_marker_with_fields(tmp_path: Path) -> None:
    """MaintenanceModeManager.down writes a marker file with all expected fields."""
    marker_path = tmp_path / "down"
    manager = MaintenanceModeManager(marker_path=marker_path)
    marker = manager.down(secret="abc", retry=60, refresh=10, template=None)
    assert marker_path.exists()
    assert marker.secret == "abc"
    assert marker.retry == 60
    assert marker.refresh == 10


def test_manager_up_clears_marker(tmp_path: Path) -> None:
    marker_path = tmp_path / "down"
    manager = MaintenanceModeManager(marker_path=marker_path)
    manager.down(secret="abc")
    assert marker_path.exists()
    manager.up()
    assert not marker_path.exists()


# ─── MaintenanceModeMiddleware ASGI behavior ─────────────────────────────────
#
# These tests use Starlette's TestClient against a minimal ASGI app wrapped in
# the middleware. The fake_asgi_app just returns 200 OK.


@pytest.fixture
def make_test_client() -> Any:
    """Returns a function that builds a TestClient against the middleware."""
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient

    def _build(marker_path: Path) -> TestClient:
        async def homepage(request: Any) -> PlainTextResponse:
            return PlainTextResponse("ok")

        app = Starlette(routes=[Route("/", homepage)])
        manager = MaintenanceModeManager(marker_path=marker_path)
        app.add_middleware(MaintenanceModeMiddleware, manager=manager)
        return TestClient(app)

    return _build


def test_middleware_passes_through_when_no_marker(tmp_path: Path, make_test_client: Any) -> None:
    """request without marker is served normally."""
    client = make_test_client(tmp_path / "down")
    response = client.get("/")
    assert response.status_code == 200
    assert response.text == "ok"


def test_middleware_returns_503_when_marker_and_no_bypass(
    tmp_path: Path,
    make_test_client: Any,
) -> None:
    """request with marker + no bypass returns 503."""
    marker_path = tmp_path / "down"
    manager = MaintenanceModeManager(marker_path=marker_path)
    manager.down(secret="test-secret")
    client = make_test_client(marker_path)
    response = client.get("/")
    assert response.status_code == 503


def test_middleware_sets_retry_after_header(tmp_path: Path, make_test_client: Any) -> None:
    """503 response includes Retry-After when configured."""
    marker_path = tmp_path / "down"
    manager = MaintenanceModeManager(marker_path=marker_path)
    manager.down(secret="test-secret", retry=120)
    client = make_test_client(marker_path)
    response = client.get("/")
    assert response.status_code == 503
    assert response.headers.get("Retry-After") == "120"


def test_middleware_bypass_via_query_param_sets_cookie(
    tmp_path: Path,
    make_test_client: Any,
) -> None:
    """?bypass=<secret> sets cookie and passes through."""
    marker_path = tmp_path / "down"
    manager = MaintenanceModeManager(marker_path=marker_path)
    manager.down(secret="my-secret")
    client = make_test_client(marker_path)
    response = client.get("/?bypass=my-secret")
    assert response.status_code == 200
    # SR-023-002: cookie is HttpOnly + SameSite=Lax
    set_cookie = response.headers.get("set-cookie", "").lower()
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie


def test_middleware_bypass_cookie_passes_through(
    tmp_path: Path,
    make_test_client: Any,
) -> None:
    """existing bypass cookie passes through without query param."""
    marker_path = tmp_path / "down"
    manager = MaintenanceModeManager(marker_path=marker_path)
    manager.down(secret="my-secret")
    client = make_test_client(marker_path)
    client.cookies.set("arvel_bypass", "my-secret")
    response = client.get("/")
    assert response.status_code == 200


def test_middleware_rejects_wrong_bypass_secret(
    tmp_path: Path,
    make_test_client: Any,
) -> None:
    """SR-023-002 (constant-time): wrong secret in query returns 503."""
    marker_path = tmp_path / "down"
    manager = MaintenanceModeManager(marker_path=marker_path)
    manager.down(secret="real-secret")
    client = make_test_client(marker_path)
    response = client.get("/?bypass=wrong-secret")
    assert response.status_code == 503
