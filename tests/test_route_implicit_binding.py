"""R1 — implicit route-model binding: a controller action typed ``show(self, user: User)``
resolves ``{user}`` to a model via its route key, 404 on a
miss - with no explicit ``Route.model`` registration. Grounded in knowledge/port/05-routing.md
(routing section 36-44). The HTTP layer duck-types models (``resolve_route_binding``) to avoid
importing the database layer."""

from __future__ import annotations

from typing import Any

from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.routing import Router


class _User:
    """A stand-in model exposing the duck-typed binding hook (matches Model.resolve_route_binding)."""

    _rows = {"1": "Ada", "2": "Linus"}

    def __init__(self, name: str) -> None:
        self.name = name

    @classmethod
    async def resolve_route_binding(cls, value: Any, field: str | None = None) -> _User | None:
        name = cls._rows.get(str(value))
        return cls(name) if name is not None else None


async def _show(request: Any, user: _User) -> dict[str, Any]:
    return {"name": user.name}


def _client() -> TestClient[Any]:
    router = Router()
    router.get("/users/{user}", _show)  # NOTE: no router.model(...) — binding is implicit
    kernel = HttpKernel()
    router.apply_to(kernel)
    return TestClient(kernel.build())


def test_implicit_binding_resolves_from_type_hint() -> None:
    with _client() as client:
        assert client.get("/users/1").json() == {"name": "Ada"}
        assert client.get("/users/2").json() == {"name": "Linus"}


def test_implicit_binding_404_on_miss() -> None:
    with _client() as client:
        assert client.get("/users/999").status_code == 404


def test_non_model_param_is_left_untouched() -> None:
    """A param whose hint is not a model (here: a plain str) passes through unbound."""

    async def _echo(request: Any, slug: str) -> dict[str, Any]:
        return {"slug": slug}

    router = Router()
    router.get("/posts/{slug}", _echo)
    kernel = HttpKernel()
    router.apply_to(kernel)
    with TestClient(kernel.build()) as client:
        assert client.get("/posts/hello").json() == {"slug": "hello"}
