"""Route-level middleware Protocol and built-in middlewares."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Protocol, runtime_checkable

from starlette.middleware.cors import CORSMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp

from arvel.http.exceptions import (
    CsrfMismatchException,
    ThrottleException,
    UnauthenticatedException,
)
from arvel.http.ratelimit import InMemoryStore, RateLimiterStore
from arvel.support.secure_compare import constant_time_equals

CallNext = Callable[[Any], Awaitable[Any]]


@runtime_checkable
class Middleware(Protocol):
    """Route-level middleware. Composed by the ``arvel.support.Pipeline``."""

    async def handle(self, request: Any, call_next: CallNext) -> Any: ...


# ───────────────────────── CORS (app-level Starlette) ─────────────────────────


class Cors(CORSMiddleware):
    """Hardened wrapper around Starlette's CORSMiddleware.

    Refuses the wildcard origin with credentials — a well-known browser footgun.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        allowed_origins: Sequence[str] = (),
        allowed_methods: Sequence[str] = ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"),
        allowed_headers: Sequence[str] = ("Authorization", "Content-Type", "X-Requested-With"),
        allow_credentials: bool = False,
        max_age: int = 600,
    ) -> None:
        if allow_credentials and any(o == "*" for o in allowed_origins):
            msg = "CORS: cannot combine wildcard origin '*' with allow_credentials=True."
            raise ValueError(msg)
        super().__init__(
            app,
            allow_origins=list(allowed_origins),
            allow_methods=list(allowed_methods),
            allow_headers=list(allowed_headers),
            allow_credentials=allow_credentials,
            max_age=max_age,
        )


# ───────────────────────── Throttle (route-level) ─────────────────────────


def _default_key(request: Any) -> str:
    client = getattr(request, "client", None)
    if client is not None and getattr(client, "host", None):
        return f"ip:{client.host}"
    return "ip:unknown"


class Throttle:
    """Rate-limit by key. Adds X-RateLimit-* headers on every response."""

    def __init__(
        self,
        max_attempts: int,
        *,
        decay_seconds: int = 60,
        key: Callable[[Any], str] | None = None,
        store: RateLimiterStore | None = None,
    ) -> None:
        if max_attempts < 1:
            msg = "Throttle: max_attempts must be >= 1."
            raise ValueError(msg)
        self._max = max_attempts
        self._decay = decay_seconds
        self._key = key or _default_key
        self._store: RateLimiterStore = store if store is not None else InMemoryStore()

    async def handle(self, request: Any, call_next: CallNext) -> Any:
        bucket = self._key(request)
        attempt = await self._store.hit(bucket, decay_seconds=self._decay)
        if attempt.count > self._max:
            raise ThrottleException(
                "Too many requests.",
                retry_after_seconds=max(self._decay, 1),
            )
        response = await call_next(request)
        remaining = max(self._max - attempt.count, 0)
        # Only inject headers when the handler returned a Response object.
        # Raw dicts / Pydantic models are serialized by FastAPI after this
        # middleware returns — wrapping them in JSONResponse would bypass
        # FastAPI's response_model validation (H-008).
        if isinstance(response, Response):
            response.headers["X-RateLimit-Limit"] = str(self._max)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response


# ───────────────────────── Authenticate (route-level) ─────────────────────────


class Authenticate:
    """Resolves ``request.state.user`` via a named guard from AuthManager.

    ``guard_name`` selects the guard configured in ``config/auth.py``.
    Defaults to ``"web"``, which maps to ``AuthManager.guard(None)``.
    """

    def __init__(self, guard_name: str = "web") -> None:
        self._guard_name = guard_name

    async def handle(self, request: Any, call_next: CallNext) -> Any:
        from arvel.auth.manager import AuthManager  # local import: avoid module-load cycle

        app = getattr(request, "app", None)
        container = getattr(getattr(app, "state", None), "arvel_container", None)
        if container is None:
            raise UnauthenticatedException("Authentication unavailable.")

        manager = container.make(AuthManager)
        guard = manager.guard(self._guard_name)
        user = await guard.user(request)
        if user is None:
            raise UnauthenticatedException("Not authenticated.")
        request.state.user = user
        _bind_user_to_context(user)
        return await call_next(request)


def _bind_user_to_context(user: object) -> None:
    """Bind the authenticated user's opaque id into the request Context.

    Logs emitted for the rest of the request carry ``user_id`` automatically.
    Only the id is bound — never the email or name (A09).
    """
    from arvel.context import Context

    user_id = getattr(user, "id", None)
    if user_id is not None:
        Context.add("user_id", str(user_id))


# ───────────────────────── CSRF (route-level) ─────────────────────────


_CSRF_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_CSRF_SESSION_KEY = "_csrf_token"
_CSRF_HEADER = "X-CSRF-Token"
_XSRF_HEADER = "X-XSRF-TOKEN"
_CSRF_FIELD = "_token"
_FORM_CONTENT_TYPE = "application/x-www-form-urlencoded"


async def _submitted_csrf_token(request: Any) -> str | None:
    """Token from the request, in Laravel's order: header, XSRF header, _token field.

    The ``_token`` form field is read only for urlencoded posts — we don't buffer
    JSON or multipart (upload) bodies just to look for a token that lives in a header.
    """
    headers = getattr(request, "headers", None)
    if headers is not None:
        for name in (_CSRF_HEADER, _XSRF_HEADER):
            value = headers.get(name)
            if value:
                return str(value)
        content_type = (headers.get("content-type") or "").split(";", 1)[0].strip().lower()
    else:
        content_type = ""

    if content_type == _FORM_CONTENT_TYPE:
        # Annotated Any so pyright doesn't collapse the callable() guard to `object`.
        form_getter: Any = getattr(request, "form", None)
        if form_getter is not None:
            form: Any = await form_getter()
            field = form.get(_CSRF_FIELD)
            if field:
                return str(field)
    return None


class VerifyCsrf:
    """Double-submit CSRF check. Skips safe methods and ``except_paths``.

    Uses ``constant_time_equals`` for timing-safe token comparison.
    """

    def __init__(self, except_paths: Sequence[str] | None = None) -> None:
        self._except = tuple(except_paths or ())

    async def handle(self, request: Any, call_next: CallNext) -> Any:
        method = (getattr(request, "method", "GET") or "GET").upper()
        path = getattr(getattr(request, "url", None), "path", "") or ""
        if method in _CSRF_SAFE_METHODS or any(path.startswith(p) for p in self._except):
            return await call_next(request)

        # Starlette's request.session is dict-like but untyped; the explicit
        # branch annotation pins the dict's type parameters so .get() doesn't
        # leak Unknown.
        raw_session: object = getattr(request, "session", None) or {}
        if isinstance(raw_session, dict):
            # isinstance narrows dict params to Unknown under pyright; widen here.
            session: dict[str, Any] = raw_session  # pyright: ignore[reportUnknownVariableType]
        else:
            session = {}
        token: Any = session.get(_CSRF_SESSION_KEY)
        sent = await _submitted_csrf_token(request)

        if not token or not sent or not constant_time_equals(str(token), str(sent)):
            raise CsrfMismatchException("CSRF token mismatch.")
        return await call_next(request)


__all__ = [
    "Authenticate",
    "CallNext",
    "Cors",
    "Middleware",
    "Throttle",
    "VerifyCsrf",
]
