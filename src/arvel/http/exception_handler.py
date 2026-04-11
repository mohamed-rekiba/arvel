"""RFC 9457 Problem Details exception handler.

Formats all HTTP errors as Problem Details JSON. In production mode
(debug=False), internal details are suppressed.

Supports domain exception registration: map any exception type to
an HTTP status code so the handler returns the correct Problem Details.
"""

from __future__ import annotations

import traceback
from typing import TYPE_CHECKING, Any

from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import DBAPIError as SADBAPIError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from arvel.data.exceptions import IntegrityError, NotFoundError
from arvel.foundation.exceptions import ArvelError
from arvel.http.exceptions import HttpException
from arvel.logging import Log
from arvel.security.exceptions import AuthenticationError, AuthorizationError

_SCOPE_CONTEXT_KEY = "arvel_context"

if TYPE_CHECKING:
    from fastapi import FastAPI, Request

logger = Log.named("arvel.http.exceptions")


def _extract_exc_context(exc: Exception) -> dict[str, Any]:
    """Pull investigation-friendly fields from an exception.

    Returns structured attributes from ArvelError subclasses (e.g.
    ``engine``, ``index``, ``model_name``) plus the originating source
    location so you know *where* it happened at a glance.
    """
    ctx: dict[str, Any] = {}

    tb = exc.__traceback__
    if tb is not None:
        while tb.tb_next is not None:
            tb = tb.tb_next
        frame = tb.tb_frame
        ctx["origin"] = f"{frame.f_code.co_filename}:{tb.tb_lineno} in {frame.f_code.co_name}"

    if isinstance(exc, ArvelError):
        for attr in vars(exc):
            if attr.startswith("_"):
                continue
            ctx[attr] = getattr(exc, attr)

    chain = exc.__cause__ or exc.__context__
    if chain is not None:
        ctx["caused_by"] = f"{type(chain).__name__}: {chain}"

    return ctx


def _extract_request_context(request: Request) -> dict[str, Any]:
    """Pull key request identifiers and application context for log correlation.

    Reads the full ``Context`` snapshot from the ASGI scope (written by
    ``ContextMiddleware`` before flushing).  This includes ``request_id``
    plus any keys added by service providers (``tenant_id``, ``user_id``,
    ``correlation_id``, …).  Falls back to the legacy ``arvel_request_id``
    scope key for backwards compatibility.
    """
    ctx: dict[str, Any] = {
        "method": request.method,
        "url": str(request.url),
    }

    app_ctx: dict[str, Any] = request.scope.get(_SCOPE_CONTEXT_KEY, {})
    if app_ctx:
        ctx.update(app_ctx)

    if "request_id" not in ctx:
        rid: str = request.scope.get("arvel_request_id", "")
        if rid:
            ctx["request_id"] = rid

    client = request.client
    if client is not None:
        ctx["client"] = f"{client.host}:{client.port}"

    query = str(request.query_params)
    if query:
        ctx["query"] = query

    user_agent = request.headers.get("user-agent")
    if user_agent:
        ctx["user_agent"] = user_agent[:120]

    return ctx


_DOMAIN_EXCEPTION_MAP: dict[type[Exception], int] = {
    NotFoundError: 404,
    AuthenticationError: 401,
    AuthorizationError: 403,
    IntegrityError: 409,
}


def register_domain_exception(exc_type: type[Exception], status_code: int) -> None:
    """Register a custom domain exception to an HTTP status code."""
    _DOMAIN_EXCEPTION_MAP[exc_type] = status_code


def register_exception(app: FastAPI) -> None:
    """Wire domain exceptions into the app's exception handlers."""
    for exc_type, status_code in _DOMAIN_EXCEPTION_MAP.items():
        _register_one(app, exc_type, status_code)


def _register_one(app: FastAPI, exc_type: type[Exception], status_code: int) -> None:
    @app.exception_handler(exc_type)
    async def _handler(
        request: Request, exc: Exception, _status: int = status_code
    ) -> JSONResponse:
        req_ctx = _extract_request_context(request)
        logger.warning(
            "domain_exception",
            exc_type=type(exc).__name__,
            status=_status,
            detail=str(exc),
            **req_ctx,
            **_extract_exc_context(exc),
        )
        headers: dict[str, str] = {}
        rid = req_ctx.get("request_id", "")
        if rid:
            headers["x-request-id"] = rid
        return _build_problem(
            status=_status,
            title=_status_phrase(_status),
            detail=str(exc),
            instance=request.url.path,
            headers=headers or None,
        )


def install_exception_handlers(app: FastAPI, *, debug: bool = False) -> None:
    """Register RFC 9457 Problem Details handlers on a FastAPI app."""
    register_exception(app)

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _build_problem(
            status=exc.status_code,
            title=_status_phrase(exc.status_code),
            detail=str(exc.detail) if exc.detail else None,
            instance=request.url.path,
            debug=debug,
        )

    @app.exception_handler(HttpException)
    async def _arvel_http_exception(request: Request, exc: HttpException) -> JSONResponse:
        return _build_problem(
            status=exc.status_code,
            title=_status_phrase(exc.status_code),
            detail=exc.detail or None,
            instance=request.url.path,
            debug=debug,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exception(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        detail = "; ".join(
            f"{'.'.join(str(loc) for loc in e.get('loc', []))}: {e.get('msg', '')}" for e in errors
        )
        return _build_problem(
            status=422,
            title="Validation Error",
            detail=detail,
            instance=request.url.path,
            debug=debug,
            extra={"errors": errors} if debug else None,
        )

    @app.exception_handler(SADBAPIError)
    async def _database_exception(request: Request, exc: SADBAPIError) -> JSONResponse:
        req_ctx = _extract_request_context(request)
        logger.error(
            "database_error",
            exc_type=type(exc).__name__,
            exc_message=str(exc),
            **req_ctx,
            **_extract_exc_context(exc),
        )
        headers: dict[str, str] = {}
        rid = req_ctx.get("request_id", "")
        if rid:
            headers["x-request-id"] = rid
        detail: str | None = None
        if debug:
            detail = f"{type(exc.orig).__name__}: {exc.orig}" if exc.orig else str(exc)
        return _build_problem(
            status=500,
            title="Internal Server Error",
            detail=detail or "A database error occurred.",
            instance=request.url.path,
            debug=debug,
            headers=headers or None,
        )

    @app.exception_handler(Exception)
    async def _unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        compact_tb = "".join(traceback.format_exception(exc)).rstrip()
        req_ctx = _extract_request_context(request)
        logger.error(
            "unhandled_exception",
            exc_type=type(exc).__name__,
            exc_message=str(exc),
            **req_ctx,
            **_extract_exc_context(exc),
            traceback=compact_tb,
        )
        detail: str | None = None
        if debug:
            detail = f"{type(exc).__name__}: {exc}"
        headers: dict[str, str] = {}
        rid = req_ctx.get("request_id", "")
        if rid:
            headers["x-request-id"] = rid
        return _build_problem(
            status=500,
            title="Internal Server Error",
            detail=detail or "An unexpected error occurred.",
            instance=request.url.path,
            debug=debug,
            headers=headers or None,
        )


_STATUS_PHRASES: dict[int, str] = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    409: "Conflict",
    422: "Unprocessable Entity",
    429: "Too Many Requests",
    500: "Internal Server Error",
    502: "Bad Gateway",
    503: "Service Unavailable",
}


def _status_phrase(code: int) -> str:
    return _STATUS_PHRASES.get(code, f"HTTP {code}")


def _build_problem(
    *,
    status: int,
    title: str,
    detail: str | None = None,
    instance: str | None = None,
    debug: bool = False,
    extra: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": title,
        "status": status,
    }
    if detail:
        body["detail"] = detail
    if instance:
        body["instance"] = instance
    if extra and debug:
        body.update(extra)

    return JSONResponse(
        status_code=status,
        content=body,
        media_type="application/problem+json",
        headers=headers,
    )
