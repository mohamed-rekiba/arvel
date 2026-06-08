"""HttpException hierarchy + HttpExceptionHandler."""

from __future__ import annotations

from typing import cast

import httpx2 as httpx
import pytest


@pytest.mark.parametrize(
    ("exc_class_name", "status", "code"),
    [
        ("BadRequestException", 400, "BAD_REQUEST"),
        ("ValidationException", 422, "VALIDATION_FAILED"),
        ("UnauthenticatedException", 401, "UNAUTHENTICATED"),
        ("AuthorizationException", 403, "FORBIDDEN"),
        ("NotFoundException", 404, "NOT_FOUND"),
        ("MethodNotAllowedException", 405, "METHOD_NOT_ALLOWED"),
        ("ConflictException", 409, "CONFLICT"),
        ("ServerErrorException", 500, "INTERNAL_ERROR"),
    ],
)
def test_exception_canonical_status_and_code(exc_class_name: str, status: int, code: str) -> None:
    import arvel.http.exceptions as ex_mod

    cls = getattr(ex_mod, exc_class_name)
    assert cls.status_code == status
    assert cls.code == code
    assert issubclass(cls, ex_mod.HttpException)


def test_throttle_exception_carries_retry_after() -> None:
    from arvel.http.exceptions import ThrottleException

    exc = ThrottleException("too many", retry_after_seconds=30)
    assert exc.status_code == 429
    assert exc.code == "TOO_MANY_REQUESTS"
    assert exc.retry_after_seconds == 30


def test_exception_to_dict_matches_api_design_shape() -> None:
    from arvel.http.exceptions import NotFoundException

    body = NotFoundException("User not found", details=[{"field": "id"}]).to_dict()
    assert body == {
        "error": {
            "code": "NOT_FOUND",
            "message": "User not found",
            "details": [{"field": "id"}],
        }
    }


def test_exception_handler_returns_json_for_api_path() -> None:
    from arvel.http.exceptions import HttpExceptionHandler, NotFoundException
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    app = FastAPI()
    HttpExceptionHandler().register(app)

    @app.get("/api/missing")
    async def handler() -> dict[str, str]:
        raise NotFoundException("missing")

    del handler  # registered via @app.get; drop local binding
    resp = cast("httpx.Client", TestClient(app)).get("/api/missing")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"
    assert resp.json()["error"]["message"] == "missing"


def test_exception_handler_never_leaks_traceback_in_response() -> None:
    from arvel.http.exceptions import HttpExceptionHandler, ServerErrorException
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    app = FastAPI()
    HttpExceptionHandler().register(app)

    @app.get("/boom")
    async def handler() -> dict[str, str]:
        raise ServerErrorException("kaboom")

    del handler  # registered via @app.get; drop local binding
    resp = cast("httpx.Client", TestClient(app)).get(
        "/boom", headers={"Accept": "application/json"}
    )
    assert resp.status_code == 500
    body = resp.text
    forbidden = ["Traceback", 'File "', "line ", "raise ServerErrorException"]
    for needle in forbidden:
        assert needle not in body, f"Leaked traceback fragment {needle!r} in response body"
