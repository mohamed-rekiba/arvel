"""HTTP response helpers — abort(), abort_if(), abort_unless()."""

from __future__ import annotations

from typing import Any

from arvel.http.exceptions import (
    AuthorizationException,
    BadRequestException,
    ConflictException,
    HttpException,
    MethodNotAllowedException,
    NotFoundException,
    ServerErrorException,
    ThrottleException,
    UnauthenticatedException,
    UnprocessableException,
)

_HTTP_TOO_MANY_REQUESTS = 429

_MESSAGES: dict[int, str] = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    409: "Conflict",
    422: "Unprocessable Entity",
    429: "Too Many Requests",
    500: "Internal Server Error",
}

_TYPED: dict[int, type[HttpException]] = {
    400: BadRequestException,
    401: UnauthenticatedException,
    403: AuthorizationException,
    404: NotFoundException,
    405: MethodNotAllowedException,
    409: ConflictException,
    422: UnprocessableException,
    500: ServerErrorException,
}


def abort(status_code: int, message: str | None = None) -> None:
    """Raise a typed HttpException subclass matching the given status code.

    Raises immediately — never returns.
    """
    msg = message or _MESSAGES.get(status_code, "Error")
    if status_code == _HTTP_TOO_MANY_REQUESTS:
        raise ThrottleException(msg, retry_after_seconds=0)
    exc_class = _TYPED.get(status_code)
    if exc_class is not None:
        raise exc_class(msg)
    raise HttpException(msg, status_code=status_code)


def abort_if(condition: Any, status_code: int, message: str | None = None) -> None:
    """Call abort() when *condition* is truthy."""
    if condition:
        abort(status_code, message)


def abort_unless(condition: Any, status_code: int, message: str | None = None) -> None:
    """Call abort() when *condition* is falsy."""
    if not condition:
        abort(status_code, message)


__all__ = ["abort", "abort_if", "abort_unless"]
