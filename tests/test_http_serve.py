"""C4c — uploads, generated OpenAPI, and as_asgi through the Application."""

from __future__ import annotations

from typing import Any

from litestar.testing import TestClient

from arvel import Application
from arvel.http import HttpKernel
from arvel.routing import Router


async def _upload(request: Any) -> dict[str, Any]:
    avatar = await request.file("avatar")
    content = await avatar.read()
    return {"name": avatar.filename, "size": len(content)}


def test_file_upload() -> None:
    kernel = HttpKernel()
    kernel.post("/upload", _upload)
    with TestClient(kernel.build()) as client:
        response = client.post("/upload", files={"avatar": ("a.txt", b"hello")})
    assert response.status_code == 201
    assert response.json() == {"name": "a.txt", "size": 5}


def test_openapi_is_generated_from_routes() -> None:
    kernel = HttpKernel()
    kernel.get("/ping", lambda request: {"pong": True})
    schema = kernel.openapi()
    assert schema["openapi"].startswith("3.")
    assert "/ping" in schema["paths"]


def test_application_as_asgi_serves_router_routes() -> None:
    app = Application()
    router = Router()
    router.get("/ping", lambda request: {"pong": True})
    app.singleton("router", lambda _app: router)

    asgi = app.as_asgi()
    with TestClient(asgi) as client:
        assert client.get("/ping").json() == {"pong": True}
