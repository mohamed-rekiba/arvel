"""C5c — route-model binding (implicit) + enum binding (404 on miss)."""

from __future__ import annotations

import enum
from typing import Any, Self

from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.routing import Router


class FakeUser:
    _store = {"1": "ada", "2": "bob"}

    def __init__(self, name: str) -> None:
        self.name = name

    @classmethod
    async def find(cls, key: Any) -> Self | None:
        name = cls._store.get(str(key))
        return cls(name) if name is not None else None


class Color(enum.Enum):
    RED = "red"
    BLUE = "blue"


async def _show_user(request: Any, user: FakeUser) -> dict[str, Any]:
    return {"name": user.name}


async def _show_color(request: Any, color: Color) -> dict[str, Any]:
    return {"color": color.value}


def _client() -> TestClient[Any]:
    router = Router()
    router.get("/users/{user}", _show_user)
    router.model("user", FakeUser)
    router.get("/colors/{color}", _show_color)
    router.bind_enum("color", Color)
    kernel = HttpKernel()
    router.apply_to(kernel)
    return TestClient(kernel.build())


def test_model_binding_resolves_instance() -> None:
    with _client() as client:
        assert client.get("/users/1").json() == {"name": "ada"}
        assert client.get("/users/2").json() == {"name": "bob"}


def test_model_binding_404_on_miss() -> None:
    with _client() as client:
        assert client.get("/users/999").status_code == 404


def test_enum_binding_resolves_member() -> None:
    with _client() as client:
        assert client.get("/colors/red").json() == {"color": "red"}


def test_enum_binding_404_on_invalid() -> None:
    with _client() as client:
        assert client.get("/colors/green").status_code == 404
