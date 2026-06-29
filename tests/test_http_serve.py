"""C4c — uploads, generated OpenAPI, and as_asgi through the Application."""

from __future__ import annotations

from typing import Any

from litestar.testing import TestClient

from arvel import Application, Model
from arvel.http import HttpKernel
from arvel.routing import Router


class _Widget(Model):
    __fields__ = {"name": str}
    __fillable__ = ["name"]


def test_handler_can_return_a_model() -> None:
    """Laravel parity: returning an Eloquent model from a controller serializes to JSON. The kernel
    registers a type-encoder for the arvel Model (→ to_dict()) so this works without a 500."""
    kernel = HttpKernel()
    kernel.get("/widget", lambda request: _Widget(id=1, name="sprocket"))
    with TestClient(kernel.build()) as client:
        resp = client.get("/widget")
    assert resp.status_code == 200
    assert resp.json() == {"id": 1, "name": "sprocket"}


def test_handler_can_return_a_list_of_models() -> None:
    """A returned collection of models serializes element-by-element (Laravel returns a JSON array)."""
    kernel = HttpKernel()
    kernel.get("/widgets", lambda request: [_Widget(id=1, name="a"), _Widget(id=2, name="b")])
    with TestClient(kernel.build()) as client:
        resp = client.get("/widgets")
    assert resp.status_code == 200
    assert resp.json() == [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]


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
