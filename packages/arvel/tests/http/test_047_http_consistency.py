"""HTTP Consistency cluster — , 13.

Tests are FAILING before the fix and PASSING after.

): HttpServiceProvider must register HttpExceptionHandler as default.
): abort() must raise typed subclass with correct code.
): Application.into_asgi() must wire scope middleware.
): HttpExceptionHandler must register catch-all Exception handler.
"""

from __future__ import annotations

import asyncio
from typing import cast

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request as _Request

# HttpServiceProvider default handler


class TestStory10DefaultExceptionHandler:
    """HttpServiceProvider must bind HttpExceptionHandler, not ProblemDetailsHandler."""

    def test_http_service_provider_binds_http_exception_handler(self) -> None:
        """Currently FAILS: provider binds ProblemDetailsHandler."""
        from arvel.application.application import Application
        from arvel.http.exceptions import HttpExceptionHandler

        app = Application()
        app.register()

        bound = app.container.make(HttpExceptionHandler)
        # After fix: must be a real HttpExceptionHandler, not ProblemDetailsHandler
        assert type(bound).__name__ == "HttpExceptionHandler"

    def test_error_response_uses_error_envelope(self) -> None:
        """Default handler must produce {error: {code, message}} shape.

        Currently FAILS: default produces RFC 7807 {type, title, status, detail}.
        """
        from arvel.http.exceptions import HttpExceptionHandler, NotFoundException

        handler = HttpExceptionHandler()
        fastapp = FastAPI()
        handler.register(fastapp)

        @fastapp.get("/test")
        async def _endpoint() -> dict[str, str]:
            raise NotFoundException("not here")

        del _endpoint  # registered via @fastapp.*; drop local binding
        client = cast("httpx.Client", TestClient(fastapp, raise_server_exceptions=False))
        response = client.get("/test")

        assert response.status_code == 404
        body = response.json()
        assert "error" in body
        assert body["error"]["code"] == "NOT_FOUND"

    def test_validation_error_uses_error_envelope(self) -> None:
        """Validation errors must use {error: {code: VALIDATION_FAILED, details: [...]}} shape."""
        from arvel.http.exceptions import HttpExceptionHandler
        from pydantic import BaseModel

        handler = HttpExceptionHandler()
        fastapp = FastAPI()
        handler.register(fastapp)

        class _Body(BaseModel):
            email: str
            age: int

        @fastapp.post("/validate")
        async def _endpoint(body: _Body) -> dict[str, str]:
            return {"ok": "yes"}

        del _endpoint  # registered via @fastapp.*; drop local binding
        client = cast("httpx.Client", TestClient(fastapp, raise_server_exceptions=False))
        response = client.post("/validate", json={"email": "bad", "age": "not-an-int"})

        assert response.status_code == 422
        body = response.json()
        assert "error" in body
        assert body["error"]["code"] == "VALIDATION_FAILED"
        assert "details" in body["error"]


# abort() typed codes


class TestStory11AbortTypedCodes:
    """abort(N) must raise typed exception with correct code."""

    @pytest.mark.parametrize(
        ("status_code", "expected_code"),
        [
            (400, "BAD_REQUEST"),
            (401, "UNAUTHENTICATED"),
            (403, "FORBIDDEN"),
            (404, "NOT_FOUND"),
            (409, "CONFLICT"),
            (422, "UNPROCESSABLE"),
            (429, "TOO_MANY_REQUESTS"),
            (500, "INTERNAL_ERROR"),
        ],
    )
    def test_abort_raises_typed_exception_with_correct_code(
        self, status_code: int, expected_code: str
    ) -> None:
        """Currently FAILS: abort() always raises base HttpException with code='INTERNAL_ERROR'."""
        from arvel.http.exceptions import HttpException
        from arvel.support.http_helpers import abort

        with pytest.raises(HttpException) as exc_info:
            abort(status_code)

        exc = exc_info.value
        assert exc.status_code == status_code
        # BUG: currently all abort() calls produce code="INTERNAL_ERROR"
        assert exc.code == expected_code

    def test_abort_custom_message_overrides_default(self) -> None:
        """Custom message must be preserved; code is always derived from status."""
        from arvel.http.exceptions import HttpException
        from arvel.support.http_helpers import abort

        with pytest.raises(HttpException) as exc_info:
            abort(404, "Custom not found message")

        exc = exc_info.value
        assert exc.message == "Custom not found message"
        assert exc.code == "NOT_FOUND"

    def test_abort_response_body_has_typed_code(self) -> None:
        """Integration: abort(404) in a route must produce NOT_FOUND in the response body."""
        from arvel.http.exceptions import HttpExceptionHandler

        handler = HttpExceptionHandler()
        fastapp = FastAPI()
        handler.register(fastapp)

        @fastapp.get("/item/{item_id}")
        async def _endpoint(item_id: str) -> dict[str, str]:
            from arvel.support.http_helpers import abort

            abort(404)
            return {}  # unreachable

        del _endpoint  # registered via @fastapp.*; drop local binding
        client = cast("httpx.Client", TestClient(fastapp, raise_server_exceptions=False))
        response = client.get("/item/missing")

        assert response.status_code == 404
        body = response.json()
        assert body["error"]["code"] == "NOT_FOUND"


# ArvelScopeMiddleware wired in into_asgi()


class TestStory12ScopeMiddleware:
    """into_asgi() must mount scope middleware so dep() works."""

    def test_into_asgi_creates_arvel_scope_per_request(self) -> None:
        """request.state.arvel_scope must be set by the middleware.

        Currently FAILS: no middleware creates arvel_scope.
        """
        from arvel.application.application import Application

        arvel_app = Application()
        arvel_app.register()
        asyncio.run(arvel_app.boot())

        fastapp = arvel_app.into_asgi()
        captured_scope: list[object] = []

        @fastapp.get("/scope-test")
        async def _endpoint(request: _Request) -> dict[str, bool]:
            scope = getattr(getattr(request, "state", None), "arvel_scope", None)
            captured_scope.append(scope)
            return {"has_scope": scope is not None}

        del _endpoint  # registered via @fastapp.*; drop local binding
        client = cast("httpx.Client", TestClient(fastapp, raise_server_exceptions=False))
        response = client.get("/scope-test")

        assert response.status_code == 200
        assert response.json()["has_scope"] is True
        assert captured_scope[0] is not None

    def test_dep_works_without_manual_scope_setup(self) -> None:
        """Depends(dep(MyService)) must resolve without AttributeError.

        Currently FAILS: dep() raises AttributeError on missing arvel_scope.
        """
        from arvel.application.application import Application
        from arvel.dep import dep
        from fastapi import Depends

        class _Service:
            def hello(self) -> str:
                return "hello"

        arvel_app = Application()
        arvel_app.register()
        arvel_app.container.bind(_Service, lambda: _Service())
        asyncio.run(arvel_app.boot())

        fastapp = arvel_app.into_asgi()

        _dep = Depends(dep(_Service))

        @fastapp.get("/dep-test")
        async def _endpoint(svc: _Service = _dep) -> dict[str, str]:
            return {"msg": svc.hello()}

        del _endpoint  # registered via @fastapp.*; drop local binding
        client = cast("httpx.Client", TestClient(fastapp, raise_server_exceptions=False))
        response = client.get("/dep-test")

        assert response.status_code == 200
        assert response.json()["msg"] == "hello"


# Catch-all 500 handler


class TestStory13CatchAllHandler:
    """HttpExceptionHandler must register a bare Exception handler."""

    def test_unhandled_exception_returns_500_envelope(self) -> None:
        """Bare RuntimeError must return {error: {code: INTERNAL_ERROR}} not a traceback.

        Currently FAILS: unhandled exceptions bypass Arvel's handler.
        """
        from arvel.http.exceptions import HttpExceptionHandler

        handler = HttpExceptionHandler()
        fastapp = FastAPI()
        handler.register(fastapp)

        @fastapp.get("/boom")
        async def _endpoint() -> dict[str, str]:
            raise RuntimeError("unexpected failure")

        del _endpoint  # registered via @fastapp.*; drop local binding
        client = cast("httpx.Client", TestClient(fastapp, raise_server_exceptions=False))
        response = client.get("/boom")

        assert response.status_code == 500
        body = response.json()
        assert "error" in body
        assert body["error"]["code"] == "INTERNAL_ERROR"
        assert body["error"]["message"] == "Something went wrong"
        # Must NOT leak the exception message or traceback
        assert "unexpected failure" not in response.text
        assert "Traceback" not in response.text

    def test_unhandled_exception_does_not_leak_stack_trace(self) -> None:
        """Internal paths and SQL must not appear in the response."""
        from arvel.http.exceptions import HttpExceptionHandler

        handler = HttpExceptionHandler()
        fastapp = FastAPI()
        handler.register(fastapp)

        @fastapp.get("/sql-boom")
        async def _endpoint() -> dict[str, str]:
            raise RuntimeError("SELECT * FROM users WHERE id = 1; DROP TABLE users;--")

        del _endpoint  # registered via @fastapp.*; drop local binding
        client = cast("httpx.Client", TestClient(fastapp, raise_server_exceptions=False))
        response = client.get("/sql-boom")

        assert response.status_code == 500
        assert "SELECT" not in response.text
        assert "DROP" not in response.text

    def test_http_exception_still_handled_correctly_after_catch_all(self) -> None:
        """Adding catch-all must not break typed HttpException handling."""
        from arvel.http.exceptions import HttpExceptionHandler, NotFoundException

        handler = HttpExceptionHandler()
        fastapp = FastAPI()
        handler.register(fastapp)

        @fastapp.get("/not-found")
        async def _endpoint() -> dict[str, str]:
            raise NotFoundException("the thing")

        del _endpoint  # registered via @fastapp.*; drop local binding
        client = cast("httpx.Client", TestClient(fastapp, raise_server_exceptions=False))
        response = client.get("/not-found")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"
