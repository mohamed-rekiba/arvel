"""HTTP exception hierarchy + central handler."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, ClassVar

from starlette.requests import Request
from starlette.responses import JSONResponse

from arvel.logging.facade import Log

if TYPE_CHECKING:
    from fastapi import FastAPI

# Translator maps a foreign exception (e.g. ORM error) onto an HttpException so
# the handler can render the standard envelope. Registered by the providers
# layer so the HTTP module stays free of upstream-layer imports.
# Translators target Exception, not BaseException — Starlette won't dispatch on
# the BaseException hierarchy (KeyboardInterrupt, SystemExit).
ExceptionTranslator = Callable[[Exception], "HttpException"]

_REDACT_HEADERS = frozenset({"authorization", "cookie", "set-cookie", "proxy-authorization"})
_REDACTED = "[REDACTED]"


class HttpException(Exception):
    """Base class for typed HTTP errors thrown by handlers/middleware."""

    status_code: int = 500  # subclasses override at class level; __init__ can override per-instance
    code: ClassVar[str] = "INTERNAL_ERROR"

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        details: Sequence[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code if status_code is not None else type(self).status_code
        self.details: list[dict[str, Any]] = list(details) if details else []

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "error": {
                "code": self.code,
                "message": self.message,
            }
        }
        if self.details:
            body["error"]["details"] = self.details
        return body


class BadRequestException(HttpException):
    status_code = 400
    code = "BAD_REQUEST"


class ValidationException(HttpException):
    status_code = 422
    code = "VALIDATION_FAILED"


class UnprocessableException(HttpException):
    status_code = 422
    code = "UNPROCESSABLE"


class UnauthenticatedException(HttpException):
    status_code = 401
    code = "UNAUTHENTICATED"


class AuthorizationException(HttpException):
    status_code = 403
    code = "FORBIDDEN"


class NotFoundException(HttpException):
    status_code = 404
    code = "NOT_FOUND"


class MethodNotAllowedException(HttpException):
    status_code = 405
    code = "METHOD_NOT_ALLOWED"


class ConflictException(HttpException):
    status_code = 409
    code = "CONFLICT"


class ThrottleException(HttpException):
    status_code = 429
    code = "TOO_MANY_REQUESTS"

    def __init__(
        self,
        message: str,
        *,
        retry_after_seconds: int,
        details: Sequence[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message, details=details)
        self.retry_after_seconds = retry_after_seconds


class ServerErrorException(HttpException):
    status_code = 500
    code = "INTERNAL_ERROR"


def _safe_headers(request: Request) -> dict[str, str]:
    return {
        key: (_REDACTED if key.lower() in _REDACT_HEADERS else value)
        for key, value in request.headers.items()
    }


class HttpExceptionHandler:
    """Central translator: HttpException → JSON response. Wires into a FastAPI app."""

    def __init__(
        self,
        *,
        translators: Mapping[type[Exception], ExceptionTranslator] | None = None,
    ) -> None:
        # Outside-layer errors (e.g. ORM's ModelNotFoundError) get mapped to an
        # HttpException at register() time. Providers configure these; the HTTP
        # module itself stays unaware of upstream layers.
        self._translators: dict[type[Exception], ExceptionTranslator] = dict(translators or {})

    def add_translator(
        self,
        exc_type: type[Exception],
        translator: ExceptionTranslator,
    ) -> None:
        """Register a foreign exception → HttpException translator."""
        self._translators[exc_type] = translator

    def register(self, app: FastAPI) -> None:
        from fastapi.exceptions import RequestValidationError

        app.add_exception_handler(HttpException, self._handle)  # type: ignore[arg-type]
        app.add_exception_handler(RequestValidationError, self._handle_validation)
        self._register_translators(app)
        app.add_exception_handler(Exception, self._handle_unexpected)

    def _register_translators(self, app: FastAPI) -> None:
        for exc_type, translator in self._translators.items():
            app.add_exception_handler(exc_type, self._make_translated_handler(translator))

    def _make_translated_handler(
        self, translator: ExceptionTranslator
    ) -> Callable[[Request, Exception], Any]:
        async def _handle_translated(request: Request, exc: Exception) -> JSONResponse:
            return await self._handle(request, translator(exc))

        return _handle_translated

    def _log_unexpected(self, request: Request, exc: Exception) -> None:
        # exc carries the traceback; the OTel logger records it. Active Context
        # (request_id, user_id, tenant_id) is merged by the logger itself.
        Log.error(
            "http.unhandled_exception",
            exc=exc,
            exc_type=type(exc).__name__,
            path=request.url.path,
            method=request.method,
        )

    async def _handle_unexpected(self, request: Request, exc: Exception) -> JSONResponse:
        self._log_unexpected(request, exc)
        server_error = ServerErrorException("Something went wrong")
        return JSONResponse(
            status_code=500,
            content=server_error.to_dict(),
        )

    async def _handle(self, request: Request, exc: HttpException) -> JSONResponse:
        Log.warning(
            "http.exception",
            code=exc.code,
            status=exc.status_code,
            path=request.url.path,
            method=request.method,
            headers=_safe_headers(request),
        )
        headers: dict[str, str] = {}
        if isinstance(exc, ThrottleException):
            headers["Retry-After"] = str(exc.retry_after_seconds)
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict(),
            headers=headers,
        )

    async def _handle_validation(self, request: Request, exc: Exception) -> JSONResponse:
        details: list[dict[str, Any]] = []
        errors_attr = getattr(exc, "errors", None)
        if callable(errors_attr):
            errors_iter: Any = errors_attr()
            details = [
                {
                    "field": ".".join(str(p) for p in err.get("loc", ())),
                    "issue": err.get("msg", "invalid"),
                }
                for err in errors_iter
            ]
        validation = ValidationException("Validation failed.", details=details)
        return await self._handle(request, validation)
