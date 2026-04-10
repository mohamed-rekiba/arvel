"""Tests for FR-020-03.7/FR-020-03.8: MaintenanceMiddleware (ASGI).

All tests are written BEFORE implementation (QA-Pre / Stage 3a).
They must compile but FAIL until the implementation is complete.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


class TestMaintenanceMiddlewareImport:
    """FR-020-03.8: MaintenanceMiddleware is importable."""

    def test_middleware_importable(self) -> None:
        from arvel.http.maintenance_middleware import MaintenanceMiddleware  # noqa: F401


class TestMaintenanceMiddleware503Response:
    """FR-020-03.1: Returns 503 when maintenance file exists."""

    @pytest.fixture
    def maintenance_dir(self, tmp_path: Path) -> Path:
        bootstrap = tmp_path / "bootstrap"
        bootstrap.mkdir()
        return bootstrap

    def test_returns_503_when_maintenance_active(self, maintenance_dir: Path) -> None:
        from arvel.http.maintenance_middleware import MaintenanceMiddleware

        (maintenance_dir / "maintenance.json").write_text(
            json.dumps({"secret_hash": None, "allowed_ips": [], "retry_after": None})
        )

        scope: dict = {
            "type": "http",
            "method": "GET",
            "path": "/api/users",
            "headers": [],
            "query_string": b"",
        }
        response_started = False
        response_status = 0
        response_headers: list = []

        async def receive():
            return {"type": "http.request", "body": b""}

        async def send(message: dict) -> None:
            nonlocal response_started, response_status, response_headers
            if message["type"] == "http.response.start":
                response_started = True
                response_status = message["status"]
                response_headers = message.get("headers", [])

        async def app(scope, receive, send):
            pass

        maint_path = maintenance_dir / "maintenance.json"
        middleware = MaintenanceMiddleware(app, maintenance_path=maint_path)

        import asyncio

        asyncio.run(middleware(scope, receive, send))

        assert response_status == 503

    def test_passes_through_when_no_maintenance(self, maintenance_dir: Path) -> None:
        from arvel.http.maintenance_middleware import MaintenanceMiddleware

        app_called = False

        async def app(scope, receive, send):
            nonlocal app_called
            app_called = True

        maint_path = maintenance_dir / "maintenance.json"
        middleware = MaintenanceMiddleware(app, maintenance_path=maint_path)

        scope: dict = {
            "type": "http",
            "method": "GET",
            "path": "/api/users",
            "headers": [],
            "query_string": b"",
        }

        async def receive():
            return {"type": "http.request", "body": b""}

        async def send(message: dict) -> None:
            pass

        import asyncio

        asyncio.run(middleware(scope, receive, send))

        assert app_called


class TestMaintenanceMiddlewareRetryAfter:
    """FR-020-03.5: Retry-After header in 503 response."""

    def test_503_includes_retry_after_header(self, tmp_path: Path) -> None:
        from arvel.http.maintenance_middleware import MaintenanceMiddleware

        bootstrap = tmp_path / "bootstrap"
        bootstrap.mkdir()
        maint_file = bootstrap / "maintenance.json"
        maint_file.write_text(
            json.dumps({"secret_hash": None, "allowed_ips": [], "retry_after": 120})
        )

        response_headers: list = []

        async def receive():
            return {"type": "http.request", "body": b""}

        async def send(message: dict) -> None:
            nonlocal response_headers
            if message["type"] == "http.response.start":
                response_headers = message.get("headers", [])

        async def app(scope, receive, send):
            pass

        middleware = MaintenanceMiddleware(app, maintenance_path=maint_file)
        scope: dict = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [],
            "query_string": b"",
        }

        import asyncio

        asyncio.run(middleware(scope, receive, send))

        header_dict = {k: v for k, v in response_headers}
        assert header_dict.get(b"retry-after") == b"120"


class TestMaintenanceMiddlewareBypassSecret:
    """FR-020-03.2: Bypass via query param secret."""

    def test_bypass_with_correct_secret(self, tmp_path: Path) -> None:
        from arvel.http.maintenance_middleware import MaintenanceMiddleware

        secret = "my-secret"
        secret_hash = "sha256:" + hashlib.sha256(secret.encode()).hexdigest()

        bootstrap = tmp_path / "bootstrap"
        bootstrap.mkdir()
        maint_file = bootstrap / "maintenance.json"
        maint_file.write_text(
            json.dumps({"secret_hash": secret_hash, "allowed_ips": [], "retry_after": None})
        )

        app_called = False

        async def app(scope, receive, send):
            nonlocal app_called
            app_called = True

        middleware = MaintenanceMiddleware(app, maintenance_path=maint_file)
        scope: dict = {
            "type": "http",
            "method": "GET",
            "path": "/api/users",
            "headers": [],
            "query_string": b"secret=my-secret",
        }

        async def receive():
            return {"type": "http.request", "body": b""}

        async def send(message: dict) -> None:
            pass

        import asyncio

        asyncio.run(middleware(scope, receive, send))

        assert app_called

    def test_no_bypass_with_wrong_secret(self, tmp_path: Path) -> None:
        from arvel.http.maintenance_middleware import MaintenanceMiddleware

        secret_hash = "sha256:" + hashlib.sha256(b"correct-secret").hexdigest()

        bootstrap = tmp_path / "bootstrap"
        bootstrap.mkdir()
        maint_file = bootstrap / "maintenance.json"
        maint_file.write_text(
            json.dumps({"secret_hash": secret_hash, "allowed_ips": [], "retry_after": None})
        )

        response_status = 0

        async def app(scope, receive, send):
            pass

        async def receive():
            return {"type": "http.request", "body": b""}

        async def send(message: dict) -> None:
            nonlocal response_status
            if message["type"] == "http.response.start":
                response_status = message["status"]

        middleware = MaintenanceMiddleware(app, maintenance_path=maint_file)
        scope: dict = {
            "type": "http",
            "method": "GET",
            "path": "/api/users",
            "headers": [],
            "query_string": b"secret=wrong-secret",
        }

        import asyncio

        asyncio.run(middleware(scope, receive, send))

        assert response_status == 503


class TestMaintenanceMiddlewareIPBypass:
    """FR-020-03.4: Bypass via IP allowlist."""

    def test_bypass_with_allowed_ip(self, tmp_path: Path) -> None:
        from arvel.http.maintenance_middleware import MaintenanceMiddleware

        bootstrap = tmp_path / "bootstrap"
        bootstrap.mkdir()
        maint_file = bootstrap / "maintenance.json"
        maint_file.write_text(
            json.dumps(
                {
                    "secret_hash": None,
                    "allowed_ips": ["192.168.1.0/24"],
                    "retry_after": None,
                }
            )
        )

        app_called = False

        async def app(scope, receive, send):
            nonlocal app_called
            app_called = True

        middleware = MaintenanceMiddleware(app, maintenance_path=maint_file)
        scope: dict = {
            "type": "http",
            "method": "GET",
            "path": "/api/users",
            "headers": [],
            "query_string": b"",
            "client": ("192.168.1.50", 12345),
        }

        async def receive():
            return {"type": "http.request", "body": b""}

        async def send(message: dict) -> None:
            pass

        import asyncio

        asyncio.run(middleware(scope, receive, send))

        assert app_called


class TestMaintenanceMiddlewareHealthExempt:
    """FR-020-03.7: /health endpoint always passes through."""

    def test_health_endpoint_exempt(self, tmp_path: Path) -> None:
        from arvel.http.maintenance_middleware import MaintenanceMiddleware

        bootstrap = tmp_path / "bootstrap"
        bootstrap.mkdir()
        maint_file = bootstrap / "maintenance.json"
        maint_file.write_text(
            json.dumps({"secret_hash": None, "allowed_ips": [], "retry_after": None})
        )

        app_called = False

        async def app(scope, receive, send):
            nonlocal app_called
            app_called = True

        middleware = MaintenanceMiddleware(app, maintenance_path=maint_file)
        scope: dict = {
            "type": "http",
            "method": "GET",
            "path": "/health",
            "headers": [],
            "query_string": b"",
        }

        async def receive():
            return {"type": "http.request", "body": b""}

        async def send(message: dict) -> None:
            pass

        import asyncio

        asyncio.run(middleware(scope, receive, send))

        assert app_called


class TestMaintenanceMiddlewareNonHTTP:
    """Non-HTTP scopes (websocket, lifespan) always pass through."""

    def test_lifespan_passes_through(self, tmp_path: Path) -> None:
        from arvel.http.maintenance_middleware import MaintenanceMiddleware

        bootstrap = tmp_path / "bootstrap"
        bootstrap.mkdir()
        maint_file = bootstrap / "maintenance.json"
        maint_file.write_text(
            json.dumps(
                {
                    "secret_hash": None,
                    "allowed_ips": [],
                    "retry_after": None,
                }
            )
        )

        app_called = False

        async def app(scope, receive, send):
            nonlocal app_called
            app_called = True

        middleware = MaintenanceMiddleware(app, maintenance_path=maint_file)
        scope: dict = {"type": "lifespan"}

        async def receive():
            return {}

        async def send(message: dict) -> None:
            pass

        import asyncio

        asyncio.run(middleware(scope, receive, send))

        assert app_called
