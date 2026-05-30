"""Smoke test: the application boots and serves the welcome route."""

from __future__ import annotations

from bootstrap.app import create_application
from starlette.testclient import TestClient


def test_root_route_returns_welcome() -> None:
    asgi = create_application().into_asgi()
    with TestClient(asgi) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "Welcome" in response.text or "Arvel" in response.text
