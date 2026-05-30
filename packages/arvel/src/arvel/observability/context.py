"""Async-safe request context propagation via contextvars."""

from __future__ import annotations

import re
import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass, field


def _empty_attrs() -> dict[str, object]:
    return {}


_REQUEST_ID_RE = re.compile(r"^[a-zA-Z0-9\-]{1,128}$")


@dataclass
class RequestContext:
    request_id: str | None = None
    user_id: str | None = None
    route: str | None = None
    service: str | None = None
    extra: dict[str, object] = field(default_factory=_empty_attrs)


_ctx: ContextVar[RequestContext | None] = ContextVar("_arvel_request_context", default=None)


def get_request_context() -> RequestContext:
    return _ctx.get() or RequestContext()


def set_request_context(ctx: RequestContext) -> Token[RequestContext | None]:
    return _ctx.set(ctx)


def reset_request_context(token: Token[RequestContext | None]) -> None:
    _ctx.reset(token)


def validate_request_id(value: str) -> str | None:
    """Return the value if safe, None otherwise."""
    if _REQUEST_ID_RE.match(value):
        return value
    return None


def generate_request_id() -> str:
    return str(uuid.uuid4())


__all__ = [
    "RequestContext",
    "generate_request_id",
    "get_request_context",
    "reset_request_context",
    "set_request_context",
    "validate_request_id",
]
