"""ch04 / finding A1 — HandleCors: CORS is handled by Litestar's engine, driven by config('cors')."""

from __future__ import annotations

from typing import Any

from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.kernel.application import Application
from arvel.routing import Router


async def _ok(request: Any) -> dict[str, str]:
    return {"ok": "1"}


def _client(cors: dict[str, Any] | None) -> TestClient[Any]:
    builder = Application.configure()
    if cors is not None:
        builder = builder.with_config({"cors": cors})
    app = builder.create()
    router = Router()
    router.get("/", _ok)
    kernel = HttpKernel(app=app)
    router.apply_to(kernel)
    return TestClient(kernel.build())


def _lower(headers: Any) -> set[str]:
    return {k.lower() for k in headers}


def test_cors_echoes_configured_origin() -> None:
    with _client({"allow_origins": ["https://example.com"]}) as client:
        r = client.get("/", headers={"Origin": "https://example.com"})
        assert r.headers.get("access-control-allow-origin") == "https://example.com"


def test_cors_preflight_returns_allow_methods() -> None:
    with _client({"allow_origins": ["https://example.com"], "allow_methods": ["GET", "POST"]}) as c:
        r = c.options(
            "/",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert r.status_code in (200, 204)
        assert "access-control-allow-methods" in _lower(r.headers)


def test_no_cors_config_means_no_headers() -> None:
    with _client(None) as client:
        r = client.get("/", headers={"Origin": "https://example.com"})
        assert "access-control-allow-origin" not in _lower(r.headers)


def test_cors_config_builder() -> None:
    app = (
        Application.configure().with_config({"cors": {"allow_origins": ["https://x.com"]}}).create()
    )
    assert HttpKernel(app=app)._cors_config() is not None
    assert HttpKernel()._cors_config() is None  # no app → no CORS
