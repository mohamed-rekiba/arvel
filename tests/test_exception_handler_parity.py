"""KERNEL-ERR — Laravel-parity exception-handler lifecycle (errors.md):
type-keyed reportable/renderable registration, context() merge, once-per-instance
report de-duplication, dont_report suppression, and the HTTP renderable path."""

from __future__ import annotations

from typing import Any

from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.http.response import Response
from arvel.http.response import json as json_response
from arvel.kernel.application import Application
from arvel.kernel.config import Repository
from arvel.kernel.exceptions import ExceptionHandler
from arvel.routing import Router


class _SpyLogger:
    def __init__(self) -> None:
        self.errors: list[tuple[Any, ...]] = []

    def error(self, *args: Any, **kwargs: Any) -> None:
        self.errors.append((args, kwargs))


class TeapotError(Exception):
    pass


class ContextualError(Exception):
    def context(self) -> dict[str, Any]:
        return {"order_id": 42, "kind": "should-not-override"}


class QuietError(Exception):
    pass


# --- reportable ------------------------------------------------------------


def test_reportable_callbacks_run_in_order_and_default_log_still_written() -> None:
    logger = _SpyLogger()
    handler = ExceptionHandler(logger)  # type: ignore[arg-type]
    calls: list[str] = []
    handler.reportable(TeapotError, lambda e: calls.append("first") or None)
    handler.reportable(Exception, lambda e: calls.append("second") or None)

    handler.report(TeapotError("t"))

    assert calls == ["first", "second"]
    assert len(logger.errors) == 1


def test_reportable_returning_false_stops_default_log() -> None:
    logger = _SpyLogger()
    handler = ExceptionHandler(logger)  # type: ignore[arg-type]
    calls: list[str] = []

    def stop(exc: TeapotError) -> bool:
        calls.append("cb")
        return False

    handler.reportable(TeapotError, stop)
    handler.report(TeapotError("t"))

    assert calls == ["cb"]
    assert logger.errors == []  # default write suppressed, Laravel `return false`


def test_same_instance_reported_at_most_once() -> None:
    logger = _SpyLogger()
    handler = ExceptionHandler(logger)  # type: ignore[arg-type]
    calls: list[str] = []
    handler.reportable(TeapotError, lambda e: calls.append("cb") or None)

    exc = TeapotError("t")
    handler.report(exc)
    handler.report(exc)  # same instance → deduped

    assert calls == ["cb"]
    assert len(logger.errors) == 1
    handler.report(TeapotError("other instance"))  # a new instance still reports
    assert len(logger.errors) == 2


def test_exception_context_merged_into_log_record_without_overriding_builtins() -> None:
    logger = _SpyLogger()
    handler = ExceptionHandler(logger)  # type: ignore[arg-type]

    handler.report(ContextualError("c"))

    assert len(logger.errors) == 1
    _, kwargs = logger.errors[0]
    assert kwargs["order_id"] == 42
    assert kwargs["kind"] == "ContextualError"  # builtin wins over context key


def test_dont_report_suppresses_callbacks_and_log() -> None:
    logger = _SpyLogger()
    handler = ExceptionHandler(logger)  # type: ignore[arg-type]
    calls: list[str] = []
    handler.reportable(Exception, lambda e: calls.append("cb") or None)
    handler.dont_report(QuietError)

    handler.report(QuietError("q"))

    assert calls == []
    assert logger.errors == []


# --- renderable ------------------------------------------------------------


def test_try_render_first_matching_non_none_wins() -> None:
    handler = ExceptionHandler()
    handler.renderable(TeapotError, lambda e, r: None)  # None falls through
    handler.renderable(TeapotError, lambda e, r: json_response({"teapot": True}, 418))
    handler.renderable(Exception, lambda e, r: json_response({"generic": True}, 500))

    result = handler.try_render(None, TeapotError("t"))

    assert isinstance(result, Response)
    assert result.status == 418
    assert result.content == {"teapot": True}


def test_try_render_returns_none_when_no_callback_matches() -> None:
    handler = ExceptionHandler()
    handler.renderable(TeapotError, lambda e, r: json_response({}, 418))
    assert handler.try_render(None, ValueError("v")) is None


# --- HTTP consumer path ----------------------------------------------------


async def _spill(request: Any) -> dict[str, Any]:
    raise TeapotError("short and stout")


async def _plain(request: Any) -> dict[str, Any]:
    raise ValueError("no renderable registered")


def _client() -> tuple[TestClient[Any], _SpyLogger]:
    logger = _SpyLogger()
    app = Application()
    app.instance("config", Repository({"app": {"debug": False}}))
    handler = ExceptionHandler(logger)  # type: ignore[arg-type]
    handler.renderable(TeapotError, lambda e, r: json_response({"error": "teapot"}, 418))
    app.instance("exceptions", handler)
    router = Router()
    router.get("/teapot", _spill)
    router.get("/plain", _plain)
    kernel = HttpKernel(app)
    router.apply_to(kernel)
    return TestClient(kernel.build()), logger


def test_http_renderable_response_is_served() -> None:
    client, _ = _client()
    with client:
        resp = client.get("/teapot", headers={"accept": "application/json"})
    assert resp.status_code == 418
    assert resp.json() == {"error": "teapot"}


def test_http_unregistered_exception_falls_through_to_default_render() -> None:
    client, logger = _client()
    with client:
        resp = client.get("/plain", headers={"accept": "application/json"})
    assert resp.status_code == 500
    assert resp.json()["message"] == "Server Error"
    assert logger.errors  # still reported
