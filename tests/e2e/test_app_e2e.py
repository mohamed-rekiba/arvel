"""End-to-end — a booted arvel application driven over real HTTP.

Exercises the full stack as a user would: Application.as_asgi() → Litestar → routing →
resource controller → FormRequest validation → content-negotiated errors, and a second
flow through the middleware pipeline + per-request auth. (Persistence uses an in-process
store so the HTTP loop stays self-contained; the ORM is covered by its own suites.)
"""

from __future__ import annotations

from typing import Any

from arvel import Application
from arvel.auth import current_user
from arvel.http import HttpKernel
from arvel.http.middleware import AuthenticateMiddleware
from arvel.kernel import set_application
from arvel.routing import Controller, Router
from arvel.testing import client
from arvel.validation import FormRequest, ValidationException

_STORE: dict[int, dict[str, Any]] = {}


class CreatePost(FormRequest):
    title: str


class PostsController(Controller):
    async def index(self, request: Any) -> dict[str, Any]:
        return {"posts": list(_STORE.values())}

    async def store(self, request: Any) -> dict[str, Any]:
        data = await request.validate(CreatePost)
        post_id = len(_STORE) + 1
        _STORE[post_id] = {"id": post_id, "title": data.title}
        return _STORE[post_id]

    async def show(self, request: Any, post: str) -> dict[str, Any]:
        found = _STORE.get(int(post))
        if found is None:
            raise ValidationException("Not Found", status=404)
        return found

    async def destroy(self, request: Any, post: str) -> dict[str, Any]:
        _STORE.pop(int(post), None)
        return {"deleted": True}


def _booted_app() -> Any:
    _STORE.clear()
    app = Application()
    router = Router()
    router.resource("posts", PostsController)
    app.singleton("router", lambda _app: router)
    return app.as_asgi()


def test_e2e_resource_lifecycle() -> None:
    with client(_booted_app()) as http:
        assert http.get("/posts").json() == {"posts": []}

        created = http.post("/posts", json={"title": "hello"})
        assert created.status_code == 201
        assert created.json() == {"id": 1, "title": "hello"}

        assert http.get("/posts/1").json()["title"] == "hello"
        assert http.get("/posts").json() == {"posts": [{"id": 1, "title": "hello"}]}

        assert http.post("/posts", json={}).status_code == 422  # validation fails
        assert http.get("/posts/999").status_code == 404  # not found

        assert http.delete("/posts/1").json() == {"deleted": True}
        assert http.get("/posts").json() == {"posts": []}


def test_e2e_auth_protected_route() -> None:
    app = Application()
    app.instance(
        "user_resolver",
        lambda request: {"id": 1} if request.header("authorization") else None,
    )
    set_application(app)
    try:

        async def dashboard(request: Any) -> dict[str, Any]:
            if current_user.get() is None:
                raise ValidationException("Unauthenticated", status=401)
            return {"ok": True}

        kernel = HttpKernel(app=app)
        kernel.global_middleware = [AuthenticateMiddleware]
        kernel.get("/dashboard", dashboard)
        with client(kernel.build()) as http:
            assert http.get("/dashboard").status_code == 401  # guest rejected
            authed = http.get("/dashboard", headers={"authorization": "Bearer t"})
            assert authed.json() == {"ok": True}
    finally:
        set_application(None)
