"""VerifyCsrf middleware."""

from __future__ import annotations

from typing import cast

import httpx
import pytest


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
def test_csrf_skips_safe_methods(method: str) -> None:
    from arvel.http.exceptions import HttpExceptionHandler
    from arvel.http.middleware import VerifyCsrf
    from arvel.routing import Route, Router
    from fastapi import FastAPI
    from starlette.middleware.sessions import SessionMiddleware
    from starlette.testclient import TestClient

    Router.reset_singleton()

    with Route.group(middleware=[VerifyCsrf()]):

        @Route.get("/x")
        async def get_x() -> dict[str, bool]:
            return {"ok": True}

        @Route.head("/x")
        async def head_x() -> dict[str, bool]:
            return {"ok": True}

        @Route.options("/x")
        async def opt_x() -> dict[str, bool]:
            return {"ok": True}

    del get_x, head_x, opt_x  # registered via @Route.*; drop local bindings
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="0" * 32)
    HttpExceptionHandler().register(app)
    Router.singleton().register_with_app(app)

    client = cast("httpx.Client", TestClient(app))
    resp = client.request(method, "/x")
    assert resp.status_code == 200


def test_csrf_post_without_token_returns_419() -> None:
    from arvel.http.exceptions import HttpExceptionHandler
    from arvel.http.middleware import VerifyCsrf
    from arvel.routing import Route, Router
    from fastapi import FastAPI
    from starlette.middleware.sessions import SessionMiddleware
    from starlette.testclient import TestClient

    Router.reset_singleton()

    with Route.group(middleware=[VerifyCsrf()]):

        @Route.post("/x")
        async def post_x() -> dict[str, bool]:
            return {"ok": True}

    del post_x  # registered via @Route.post; drop local binding
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="0" * 32)
    HttpExceptionHandler().register(app)
    Router.singleton().register_with_app(app)

    resp = cast("httpx.Client", TestClient(app)).post("/x", json={})
    assert resp.status_code == 419  # Laravel CSRF parity


@pytest.mark.asyncio
async def test_csrf_passes_with_matching_session_and_header() -> None:
    from types import SimpleNamespace

    from arvel.http.middleware import VerifyCsrf

    request = SimpleNamespace(
        method="POST",
        url=SimpleNamespace(path="/x"),
        session={"_csrf_token": "tok"},
        headers={"X-CSRF-Token": "tok"},
    )

    async def call_next(_: object) -> dict[str, bool]:
        return {"ok": True}

    assert await VerifyCsrf().handle(request, call_next) == {"ok": True}


@pytest.mark.asyncio
async def test_csrf_treats_non_dict_session_as_empty() -> None:
    from types import SimpleNamespace

    from arvel.http.middleware import CsrfMismatchException, VerifyCsrf

    request = SimpleNamespace(
        method="POST",
        url=SimpleNamespace(path="/x"),
        session=object(),
        headers={"X-CSRF-Token": "tok"},
    )

    async def call_next(_: object) -> dict[str, bool]:
        return {"ok": True}

    with pytest.raises(CsrfMismatchException):
        await VerifyCsrf().handle(request, call_next)


def test_csrf_except_paths_bypasses_check() -> None:
    from arvel.http.exceptions import HttpExceptionHandler
    from arvel.http.middleware import VerifyCsrf
    from arvel.routing import Route, Router
    from fastapi import FastAPI
    from starlette.middleware.sessions import SessionMiddleware
    from starlette.testclient import TestClient

    Router.reset_singleton()

    with Route.group(middleware=[VerifyCsrf(except_paths=["/webhooks/stripe"])]):

        @Route.post("/webhooks/stripe")
        async def stripe() -> dict[str, bool]:
            return {"ok": True}

    del stripe  # registered via @Route.post; drop local binding
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="0" * 32)
    HttpExceptionHandler().register(app)
    Router.singleton().register_with_app(app)

    resp = cast("httpx.Client", TestClient(app)).post("/webhooks/stripe", json={})
    assert resp.status_code == 200


def test_csrf_uses_constant_time_comparison() -> None:
    """Inspect the source for `secrets.compare_digest` usage — ."""
    import inspect

    from arvel.http.middleware import VerifyCsrf

    src = inspect.getsource(VerifyCsrf)
    assert "compare_digest" in src, "VerifyCsrf must use secrets.compare_digest"
