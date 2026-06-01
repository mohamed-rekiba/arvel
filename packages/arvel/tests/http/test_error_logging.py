"""unhandled exceptions log through the Log facade with context."""

from __future__ import annotations

from typing import cast

import httpx
from arvel.context import Context, ContextRepository, bind_repository, reset_repository
from arvel.http.exceptions import HttpExceptionHandler, NotFoundException
from arvel.testing.observability import FakeObservability
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _app() -> FastAPI:
    app = FastAPI()
    HttpExceptionHandler().register(app)

    @app.get("/boom")
    async def _boom() -> dict[str, str]:
        raise RuntimeError("db connection string leaked here")

    @app.get("/missing")
    async def _missing() -> dict[str, str]:
        raise NotFoundException("User 42 not found")

    del _boom, _missing  # registered via decorator; drop local bindings
    return app


def test_unhandled_exception_logged_via_facade() -> None:
    client = cast("httpx.Client", TestClient(_app(), raise_server_exceptions=False))

    with FakeObservability() as obs:
        response = client.get("/boom")

    assert response.status_code == 500
    records = [r for r in obs.log_records if r.body == "http.unhandled_exception"]
    assert records, "expected the unhandled exception to be logged through Log facade"
    assert records[0].attributes["exc_type"] == "RuntimeError"
    assert records[0].attributes["path"] == "/boom"


def test_500_response_hides_internal_details() -> None:
    client = cast("httpx.Client", TestClient(_app(), raise_server_exceptions=False))

    response = client.get("/boom")

    body = response.json()
    assert body == {"error": {"code": "INTERNAL_ERROR", "message": "Something went wrong"}}
    assert "db connection string" not in response.text
    assert "Traceback" not in response.text


def test_unhandled_exception_carries_request_context() -> None:
    repo = ContextRepository()
    token = bind_repository(repo)
    try:
        Context.add("request_id", "req-err-1")
        handler = HttpExceptionHandler()
        app = FastAPI()
        handler.register(app)

        @app.get("/kaboom")
        async def _kaboom() -> dict[str, str]:
            Context.add("request_id", "req-err-1")
            raise RuntimeError("nope")

        del _kaboom  # registered via decorator; drop local binding
        client = cast("httpx.Client", TestClient(app, raise_server_exceptions=False))
        with FakeObservability() as obs:
            client.get("/kaboom")

        records = [r for r in obs.log_records if r.body == "http.unhandled_exception"]
        assert records
        assert records[0].attributes.get("request_id") == "req-err-1"
    finally:
        reset_repository(token)


def test_typed_exception_message_preserved() -> None:
    client = cast("httpx.Client", TestClient(_app(), raise_server_exceptions=False))

    response = client.get("/missing")

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "User 42 not found"
