"""HTTP-layer typing-test suite — +.
Uses `typing.assert_type` to lock the public type signatures of every new symbol.
mypy --strict and pyright --strict both must accept this file, and pytest also
runs each function at collection time so unintended regressions surface as test
failures (not just static-checker noise).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, Any, assert_type

from pydantic import BaseModel


def test_route_facade_signatures_are_typed() -> None:
    from arvel.routing import Route

    # Each verb decorator factory returns a decorator that returns the original callable.
    decorator = Route.get("/users")
    assert callable(decorator)


def test_form_request_generic_resolves() -> None:
    from arvel.http.requests import FormRequest

    class P(BaseModel):
        x: int

    fr: FormRequest[P] = FormRequest(P(x=1))
    assert_type(fr.validated(), P)


def test_json_resource_generic_resolves() -> None:
    from arvel.http.resources import JsonResource

    class _D(dict[str, Any]):
        pass

    class R(JsonResource[_D]):
        def to_dict(self, request: Any) -> dict[str, object]:
            return {}

    r = R(_D())
    assert_type(r.resource, _D)


def test_middleware_protocol_accepts_user_class() -> None:
    from arvel.http.middleware import Middleware

    class MyMW:
        async def handle(
            self,
            request: Any,
            call_next: Callable[[Any], Awaitable[Any]],
        ) -> Any:
            return await call_next(request)

    mw: Middleware = MyMW()
    _ = mw


def test_user_resolver_protocol_accepts_user_class() -> None:
    from arvel.http.auth import UserResolver

    class MyResolver:
        async def by_id(self, user_id: str) -> Any | None:
            return None

        async def by_credentials(self, credentials: dict[str, object]) -> Any | None:
            return None

    r: UserResolver = MyResolver()
    _ = r


def test_no_prefix_marker_accepts_annotated() -> None:
    from arvel.config import ArvelSettings, NoPrefix

    class S(ArvelSettings):
        secret: Annotated[str, NoPrefix] = ""
        port: Annotated[int, NoPrefix] = 8080

    _ = S


def test_attempt_is_named_tuple() -> None:
    from datetime import datetime

    from arvel.http.ratelimit import Attempt

    a = Attempt(count=1, reset_at=datetime.now())  # noqa: DTZ005
    assert_type(a.count, int)


def test_all_existing_foundations_types_still_resolve() -> None:
    #  no signature break on symbols.
    from arvel import Application, Container, Scope, ServiceProvider, env

    assert_type(env("FOO", "bar"), str)  # still typed
    assert Scope.SINGLETON.value == "singleton"
    assert Container is not None
    assert Application is not None
    assert ServiceProvider is not None
