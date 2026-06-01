"""Cors middleware."""

from __future__ import annotations

import pytest


def test_cors_rejects_credentials_with_wildcard_origin() -> None:
    """Security guardrail (): never serve credentialed CORS with a wildcard origin."""
    from arvel.http.middleware import Cors
    from fastapi import FastAPI

    fa = FastAPI()

    with pytest.raises(ValueError, match="wildcard"):
        Cors(fa, allowed_origins=["*"], allow_credentials=True)


def test_cors_preflight_returns_allow_headers_for_known_origin() -> None:
    from arvel.http.middleware import Cors
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    fa = FastAPI()
    fa.add_middleware(Cors, allowed_origins=["https://app.example.com"])

    @fa.options("/api/test")
    async def options_handler() -> dict[str, bool]:
        return {"ok": True}

    @fa.get("/api/test")
    async def get_handler() -> dict[str, bool]:
        return {"ok": True}

    del options_handler, get_handler  # registered via @fa.*; drop local bindings
    client = TestClient(fa)
    resp = client.options(
        "/api/test",
        headers={
            "Origin": "https://app.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.headers.get("access-control-allow-origin") == "https://app.example.com"


def test_cors_disallowed_origin_does_not_get_allow_origin_header() -> None:
    from arvel.http.middleware import Cors
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    fa = FastAPI()
    fa.add_middleware(Cors, allowed_origins=["https://app.example.com"])

    @fa.get("/api/test")
    async def handler() -> dict[str, bool]:
        return {"ok": True}

    del handler  # registered via @fa.get; drop local binding
    client = TestClient(fa)
    resp = client.get(
        "/api/test",
        headers={"Origin": "https://evil.example.com"},
    )
    assert "access-control-allow-origin" not in {k.lower() for k in resp.headers}
