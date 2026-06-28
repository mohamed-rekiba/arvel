"""Phase 11 — golden-path: the full HTTP stack composed end-to-end.

Routing + resource controller + FormRequest validation + content-negotiated exception
rendering, served through a real Litestar app and driven by the testkit client.
"""

from __future__ import annotations

from typing import Any

from arvel.http import HttpKernel
from arvel.routing import Controller, Router
from arvel.testing import client
from arvel.validation import FormRequest, ValidationException

_STORE: dict[int, dict[str, Any]] = {}


class CreateUser(FormRequest):
    name: str
    email: str


class UserController(Controller):
    async def index(self, request: Any) -> dict[str, Any]:
        return {"users": list(_STORE.values())}

    async def store(self, request: Any) -> dict[str, Any]:
        data = await request.validate(CreateUser)
        identifier = len(_STORE) + 1
        _STORE[identifier] = {"id": identifier, "name": data.name, "email": data.email}
        return _STORE[identifier]

    async def show(self, request: Any, user: str) -> dict[str, Any]:
        found = _STORE.get(int(user))
        if found is None:
            raise ValidationException("Not Found", status=404)
        return found


def test_golden_path_resource_crud() -> None:
    _STORE.clear()
    router = Router()
    router.resource("users", UserController)
    kernel = HttpKernel()
    router.apply_to(kernel)

    with client(kernel.build()) as http:
        created = http.post("/users", json={"name": "Ada", "email": "ada@example.com"})
        assert created.status_code == 201
        assert created.json()["name"] == "Ada"

        listing = http.get("/users")
        assert listing.status_code == 200
        assert listing.json()["users"][0]["name"] == "Ada"

        shown = http.get("/users/1")
        assert shown.status_code == 200
        assert shown.json()["email"] == "ada@example.com"

        invalid = http.post("/users", json={"name": "no-email"})
        assert invalid.status_code == 422
        assert "errors" in invalid.json()

        missing = http.get("/users/999")
        assert missing.status_code == 404
