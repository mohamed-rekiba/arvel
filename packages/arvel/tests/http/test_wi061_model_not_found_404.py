"""WI-arvel-061 — Epic 049 Story 4: ORM `ModelNotFoundError` → HTTP 404 envelope.

Without an explicit translator, the ORM error falls through to the catch-all
and becomes a 500. The `HttpServiceProvider` wires `ModelNotFoundError` to a
`NotFoundException` translator so route handlers surface missing records as
the standard 404 envelope. Tests build the translator map the same way the
provider does, keeping the HTTP layer ORM-agnostic per ADR-016.
"""

from __future__ import annotations

from collections.abc import Mapping

from arvel.database.exceptions import ModelNotFoundError, ORMError
from arvel.http.exceptions import (
    ExceptionTranslator,
    HttpException,
    HttpExceptionHandler,
    NotFoundException,
)
from arvel.http.problem_details import ProblemDetailsHandler
from fastapi import FastAPI
from starlette.testclient import TestClient


def _translators() -> Mapping[type[Exception], ExceptionTranslator]:
    def _model_not_found(exc: Exception) -> HttpException:
        return NotFoundException(str(exc))

    return {ModelNotFoundError: _model_not_found}


def test_model_not_found_error_returns_404_with_envelope() -> None:
    app = FastAPI()
    HttpExceptionHandler(translators=_translators()).register(app)

    @app.get("/users/{user_id}")
    async def handler(user_id: int) -> dict[str, int]:
        raise ModelNotFoundError("User", user_id)

    del handler
    resp = TestClient(app).get("/users/99")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert "User" in body["error"]["message"]
    assert "99" in body["error"]["message"]


def test_model_not_found_error_does_not_leak_traceback() -> None:
    app = FastAPI()
    HttpExceptionHandler(translators=_translators()).register(app)

    @app.get("/posts/{slug}")
    async def handler(slug: str) -> dict[str, str]:
        raise ModelNotFoundError("Post", slug)

    del handler
    resp = TestClient(app).get("/posts/unknown")
    assert resp.status_code == 404
    body = resp.text
    forbidden = ["Traceback", 'File "', "raise ModelNotFoundError", "arvel/database"]
    for needle in forbidden:
        assert needle not in body, f"Leaked {needle!r} in body"


def test_other_orm_errors_still_propagate_to_500() -> None:
    app = FastAPI()
    HttpExceptionHandler(translators=_translators()).register(app)

    @app.get("/db-error")
    async def handler() -> dict[str, str]:
        raise ORMError("connection refused")

    del handler
    # raise_server_exceptions=False mirrors production ASGI behaviour where
    # the framework's catch-all handler returns the 500 envelope instead of
    # the test client re-raising.
    resp = TestClient(app, raise_server_exceptions=False).get("/db-error")
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "INTERNAL_ERROR"


def test_add_translator_registers_handler_after_construction() -> None:
    handler = HttpExceptionHandler()
    handler.add_translator(ModelNotFoundError, lambda exc: NotFoundException(str(exc)))
    app = FastAPI()
    handler.register(app)

    @app.get("/articles/{article_id}")
    async def view(article_id: int) -> dict[str, int]:
        raise ModelNotFoundError("Article", article_id)

    del view
    resp = TestClient(app).get("/articles/42")
    assert resp.status_code == 404
    assert set(resp.json()["error"].keys()) >= {"code", "message"}


def test_problem_details_handler_maps_model_not_found_to_rfc7807() -> None:
    app = FastAPI()
    ProblemDetailsHandler(translators=_translators()).register(app)

    @app.get("/orders/{order_id}")
    async def handler(order_id: int) -> dict[str, int]:
        raise ModelNotFoundError("Order", order_id)

    del handler
    resp = TestClient(app).get("/orders/7")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/problem+json")
    body = resp.json()
    assert body["status"] == 404
    assert body["type"].endswith("/problems/not-found")
    assert "Order" in body["detail"]


def test_provider_wires_orm_translator_by_default() -> None:
    # Smoke: the HttpServiceProvider's factory injects the ORM translator so
    # apps using the standard wiring get the 404 mapping for free.
    from arvel.providers.http_provider import default_translators

    wired = default_translators()
    assert ModelNotFoundError in wired
    translated = wired[ModelNotFoundError](ModelNotFoundError("User", 1))
    assert isinstance(translated, NotFoundException)
    assert translated.status_code == 404


def test_provider_wires_auth_exceptions_to_401_and_403() -> None:
    from arvel.auth.exceptions import AuthorizationException as AuthForbidden
    from arvel.auth.exceptions import UnauthenticatedException as AuthUnauth
    from arvel.http.exceptions import AuthorizationException, UnauthenticatedException
    from arvel.providers.http_provider import default_translators

    wired = default_translators()
    assert AuthUnauth in wired
    assert AuthForbidden in wired

    unauth = wired[AuthUnauth](AuthUnauth())
    assert isinstance(unauth, UnauthenticatedException)
    assert unauth.status_code == 401

    forbidden = wired[AuthForbidden](AuthForbidden())
    assert isinstance(forbidden, AuthorizationException)
    assert forbidden.status_code == 403


def test_auth_unauthenticated_exception_returns_401_envelope() -> None:
    from arvel.auth.exceptions import UnauthenticatedException as AuthUnauth
    from arvel.providers.http_provider import default_translators

    app = FastAPI()
    HttpExceptionHandler(translators=default_translators()).register(app)

    @app.get("/me")
    async def handler() -> dict[str, str]:
        raise AuthUnauth("token expired")

    del handler
    resp = TestClient(app, raise_server_exceptions=False).get("/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


def test_auth_authorization_exception_returns_403_envelope() -> None:
    from arvel.auth.exceptions import AuthorizationException as AuthForbidden
    from arvel.providers.http_provider import default_translators

    app = FastAPI()
    HttpExceptionHandler(translators=default_translators()).register(app)

    @app.get("/admin")
    async def handler() -> dict[str, str]:
        raise AuthForbidden

    del handler
    resp = TestClient(app, raise_server_exceptions=False).get("/admin")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"
