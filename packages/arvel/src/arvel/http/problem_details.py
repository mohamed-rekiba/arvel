"""RFC 7807 problem-details exception handler.

Every error response follows RFC 7807. The handler reads the problem-type
base URI from ``config/app.py`` (key ``"app.url"``), defaulting to
``http://localhost`` when no config file is present.

Wire it as the application exception handler in your provider::

    c.singleton(HttpExceptionHandler, ProblemDetailsHandler)

The handler is registered as the ``HttpServiceProvider`` default so that all
Arvel applications get RFC 7807 out of the box without any custom provider.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

from arvel.http.exceptions import (
    ExceptionTranslator,
    HttpException,
    HttpExceptionHandler,
    ThrottleException,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI
    from starlette.requests import Request

_TITLE_MAX_LENGTH = 80


def _problem_type_base() -> str:
    """Derive the RFC 7807 type URI base from config/app.py (key ``app.url``)."""
    from arvel.config import config

    app_url = config("app.url", "http://localhost")
    return f"{app_url.rstrip('/')}/problems"


class ProblemDetailsHandler(HttpExceptionHandler):
    """RFC 7807 problem-details response handler.

    Produces::

        {
          "type":   "https://example.com/problems/<code>",
          "title":  "Human-readable summary",
          "status": 422,
          "detail": [{"loc": [...], "msg": "..."}, ...]   # validation
           OR
          "detail": "Plain description"                   # other errors
        }

    The ``detail`` field is polymorphic: validation errors carry a list of
    field-level issues; all other errors carry a plain string. RFC 7807
    declares ``detail`` as a string but the list shape is more useful for
    form-validation consumers, and every client can safely ignore the field
    when not needed.
    """

    def register(self, app: FastAPI) -> None:
        """Install the RFC 7807 handler on ``app``, overriding the parent's wiring."""
        app.add_exception_handler(HttpException, self.handle_problem)  # type: ignore[arg-type]
        app.add_exception_handler(RequestValidationError, self.handle_validation_problem)
        for exc_type, translator in self._translators.items():
            app.add_exception_handler(exc_type, self._make_problem_handler(translator))

    def _make_problem_handler(
        self, translator: ExceptionTranslator
    ) -> Callable[[Request, Exception], Any]:
        async def _handle_translated(request: Request, exc: Exception) -> JSONResponse:
            return await self.handle_problem(request, translator(exc))

        return _handle_translated

    async def handle_problem(self, _request: Request, exc: HttpException) -> JSONResponse:
        body = self._problem_body(
            code=exc.code,
            title=_title_from_message(exc.message),
            status=exc.status_code,
            detail=exc.message,
        )
        if exc.details:
            body["detail"] = list(exc.details)

        headers: dict[str, str] = {}
        if isinstance(exc, ThrottleException):
            headers["Retry-After"] = str(exc.retry_after_seconds)

        return JSONResponse(
            status_code=exc.status_code,
            content=body,
            headers=headers,
            media_type="application/problem+json",
        )

    async def handle_validation_problem(self, _request: Request, exc: Exception) -> JSONResponse:
        details: list[dict[str, Any]] = []
        if isinstance(exc, RequestValidationError):
            details.extend(
                {
                    "loc": list(err.get("loc", ())),
                    "msg": err.get("msg", "invalid"),
                    "type": err.get("type", "value_error"),
                }
                for err in exc.errors()
            )
        body = self._problem_body(
            code="VALIDATION_FAILED",
            title="Validation failed",
            status=422,
            detail=details,
        )
        return JSONResponse(
            status_code=422,
            content=body,
            media_type="application/problem+json",
        )

    @staticmethod
    def _problem_body(
        *,
        code: str,
        title: str,
        status: int,
        detail: object,
    ) -> dict[str, Any]:
        base = _problem_type_base()
        return {
            "type": f"{base}/{code.lower().replace('_', '-')}",
            "title": title,
            "status": status,
            "detail": detail,
        }


def _title_from_message(message: str) -> str:
    candidate = message.split("\n", 1)[0].rstrip(".")
    return candidate if len(candidate) <= _TITLE_MAX_LENGTH else "Request failed"


__all__ = ["ProblemDetailsHandler"]
