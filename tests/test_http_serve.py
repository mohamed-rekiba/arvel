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
    """The kernel registers a type-encoder for Model (→ to_dict()), so returning one just works."""
    kernel = HttpKernel()
    kernel.get("/widget", lambda request: _Widget(id=1, name="sprocket"))
    with TestClient(kernel.build()) as client:
        resp = client.get("/widget")
    assert resp.status_code == 200
    assert resp.json() == {"id": 1, "name": "sprocket"}


def test_handler_can_return_a_list_of_models() -> None:
    """A returned list of models serializes element-by-element into a JSON array."""
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


def test_typed_query_params_are_injected_and_documented() -> None:
    """A handler's non-path/non-body typed args are query parameters, injected and documented."""

    async def search(request: Any, q: str | None = None, page: int = 1) -> dict[str, Any]:
        return {"q": q, "page": page}

    kernel = HttpKernel()
    kernel.get("/search", search)
    # injected with coercion + defaults
    with TestClient(kernel.build()) as client:
        assert client.get("/search?q=hat&page=3").json() == {"q": "hat", "page": 3}
        assert client.get("/search").json() == {"q": None, "page": 1}
    # documented as query parameters
    schema = kernel.openapi()
    params = schema["paths"]["/search"]["get"].get("parameters", [])
    by_name = {p["name"]: p for p in params}
    assert {"q", "page"} <= set(by_name)
    assert all(p["in"] == "query" for p in params)


def test_query_params_do_not_use_deprecated_inferred_style() -> None:
    """The adapter must declare query params explicitly (Annotated[..., Parameter()]), not lean on
    Litestar inferring them from a bare typed default — the inferred style is deprecated upstream and
    would warn on every param today and break on the next major. Any such warning fails this test."""
    import warnings

    from litestar.exceptions import LitestarDeprecationWarning

    async def search(request: Any, q: str | None = None, page: int = 1) -> dict[str, Any]:
        return {"q": q, "page": page}

    kernel = HttpKernel()
    kernel.get("/search", search)
    with warnings.catch_warnings():
        warnings.simplefilter("error", LitestarDeprecationWarning)
        with TestClient(kernel.build()) as client:
            assert client.get("/search?q=hat&page=2").json() == {"q": "hat", "page": 2}
        kernel.openapi()


def test_model_not_found_renders_as_404() -> None:
    """find_or_fail/first_or_fail raise ModelNotFound; the kernel renders it as 404."""
    from arvel.database.model import ModelNotFound

    async def show(request: Any, id: int) -> Any:
        raise ModelNotFound("No query results for model [Post].")

    kernel = HttpKernel()
    kernel.get("/posts/{id:int}", show)
    with TestClient(kernel.build()) as client:
        resp = client.get("/posts/999", headers={"accept": "application/json"})
    assert resp.status_code == 404


def test_route_status_override_lets_a_typed_post_return_200() -> None:
    """Route.post(...).status(200) overrides Litestar's default POST-201."""
    router = Router()
    router.post("/login", lambda request: {"ok": True}, name="login").status(200)
    app = Application()
    app.singleton("router", lambda _app: router)
    with TestClient(app.as_asgi()) as client:
        resp = client.post("/login")
    assert resp.status_code == 200  # not the default 201
    assert resp.json() == {"ok": True}


def test_application_as_asgi_serves_router_routes() -> None:
    app = Application()
    router = Router()
    router.get("/ping", lambda request: {"pong": True})
    app.singleton("router", lambda _app: router)

    asgi = app.as_asgi()
    with TestClient(asgi) as client:
        assert client.get("/ping").json() == {"pong": True}
