"""arvel.http.middleware — the base middleware class.

The app extends ``Middleware`` and implements ``handle(request, call_next)``; it may
short-circuit by returning a ``Response`` instead of calling ``call_next``. The
two-tier pipeline (global → group/route) is composed by the ``HttpKernel`` as a
chain of responsibility. Grounded in knowledge/port/04-http-kernel-middleware.md.
"""

from __future__ import annotations

import inspect
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Protocol, cast

import msgspec

from arvel.kernel import Settings

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from arvel.http.rate_limiter import Limit
    from arvel.http.request import Request


def _empty_str_list() -> list[str]:
    return []


class MiddlewareProtocol(Protocol):
    """Structural type for arvel's own middleware ``handle`` seam (the two-tier pipeline
    ``HttpKernel._run_pipeline`` drives): ``request`` is the typed ``Request``, ``call_next``
    forwards it to the next middleware/handler. Documents + type-checks arvel's built-ins below;
    an **app's own** middleware classes stay duck-typed (``HttpKernel`` calls ``.handle(...)`` on
    whatever it resolves, no isinstance check), so nothing outside this module need implement it
    formally."""

    async def handle(
        self, request: Request, call_next: Callable[[Request], Awaitable[Any]]
    ) -> Any: ...


class SessionSettings(Settings):
    """Typed, validated view over the ``session`` config section (DR-0016) — matches the
    scaffold's ``config/session.py`` (and the top-level-key pattern of the other Settings:
    database/cache/mail).

    ``lifetime`` is in **minutes**; the middleware
    converts it to seconds for the cookie ``max-age`` and the cache TTL. Default 120 min = 2h.

    ``host_prefix`` is ``None`` by default so it derives from ``secure`` (the ``__Host-`` prefix
    requires a Secure cookie); set it explicitly in config to force on/off.

    ``driver`` selects the server-side store: ``"cookie"`` (default) is arvel's own in-process dict
    (``StartSession``'s own default — lost on restart, not shared across workers); ``"redis"`` wires
    ``StartSession`` to the app's own bound ``"cache"`` service (``HttpKernel.use_default_groups``),
    so sessions survive restarts and are shared across every worker/host — the same Redis/Valkey
    the app already runs for caching, not a second connection. A closed set (the only two drivers
    ``StartSession`` actually branches on) — an unknown value fails config validation immediately
    instead of silently falling back to in-process.

    ``csrf_except`` — URI glob patterns (``request.is_()``-style, e.g. ``"webhooks/*"``) exempt from
    ``ValidateCsrfToken``, merged with any subclass-level override.

    ``trusted_origins`` — origins (besides the request's own host) allowed to source
    state-changing browser requests: bare hosts (``partner.example``, any scheme/port) or full
    origins (``https://partner.example:8443``).
    """

    __config_key__ = "session"
    driver: Literal["cookie", "redis"] = "cookie"
    lifetime: int = 120  # minutes; x60 for cookie max-age / cache TTL
    secure: bool = True
    host_prefix: bool | None = None
    csrf_except: list[str] = msgspec.field(default_factory=_empty_str_list)
    trusted_origins: list[str] = msgspec.field(default_factory=_empty_str_list)


# Shared across the per-request middleware instances the kernel builds: name:client -> (count, window_start).
_THROTTLE_HITS: dict[str, tuple[int, float]] = {}

# per-request rate-limit headers to attach to an allowed response — a ContextVar (not instance
# state) because a throttle middleware instance is shared across concurrent requests.
_RATE_LIMIT_HEADERS: ContextVar[dict[str, str] | None] = ContextVar(
    "arvel_rate_limit_headers", default=None
)
# Default in-process session store (session id -> data). Apps swap in a cache-backed store.
_SESSIONS: dict[str, dict[str, Any]] = {}


def reset_rate_limiter() -> None:
    """Clear the in-process rate-limiter window state.

    The default ``ThrottleRequests`` state is **process-global** — correct for one running app, but
    it leaks across the multiple app instances a test suite builds in a single process, so the api
    throttle eventually 429s spuriously mid-suite. Call this between tests (an autouse fixture) to
    isolate each test. No effect on a cache-backed (distributed) limiter — clear that store instead.
    """
    _THROTTLE_HITS.clear()


def reset_sessions() -> None:
    """Clear the default in-process session store — the session counterpart to
    :func:`reset_rate_limiter` for test isolation (no effect on a cache-backed session store)."""
    _SESSIONS.clear()


class Middleware:
    """Base middleware. Override ``handle`` to inspect/short-circuit/decorate, and (optionally)
    ``terminate`` to run *after* the response is built (session flush, logging, …)."""

    async def handle(self, request: Request, call_next: Callable[[Request], Awaitable[Any]]) -> Any:
        return await call_next(request)

    async def terminate(self, request: Any, response: Any) -> None:
        """Optional after-response hook; the kernel calls it once the response is built."""


def _default_segment(request: Any) -> str:
    """The default throttle segment key: the authenticated user's id, else the client
    IP. Prefixed so a numeric user id can never collide with an IP string."""
    from arvel.support import current_user

    user = current_user.get()
    if user is not None:
        uid = getattr(user, "id", None)
        if uid is not None:
            return f"user:{uid}"
    getter = getattr(request, "ip", None)
    client: Any = getter() if callable(getter) else None
    return f"ip:{client}" if client else "ip:global"


class ThrottleRequests(Middleware):
    """Rate-limit by client: at most ``max_attempts`` per ``decay_seconds`` window (api group).

        By default state lives in a process-shared dict keyed by ``name:client``. Pass a ``cache``
        (a ``CacheRepository``) to count over a shared backend instead — that makes limiting
        **distributed** across processes/hosts (e.g. Redis). A 429 ``ValidationException`` is raised
        when the limit is exceeded.

        Pass ``limiter_name`` instead (what the ``throttle:<name>`` route-middleware string builds,
        e.g. ``Route.get(...).middleware("throttle:api")``) to rate-limit via a **named limiter**
        registered on the app's ``limiter`` (:class:`~arvel.http.rate_limiter.RateLimiter`) with
        ``RateLimiter.for_(name, resolver)``: ``resolver(request)`` returns a
    :class:`~arvel.http.rate_limiter.Limit`, a ``list[Limit]``, or ``None`` (unlimited). A limit
        with no explicit ``.by(key)`` segments by:func:`_default_segment` (user id, else IP). Over any
        limit renders a 429 with ``Retry-After``/``X-RateLimit-Limit``/``X-RateLimit-Remaining``
        headers (or the limit's own ``.response(cb)`` builder); a successful response carries the
        ``X-RateLimit-*`` headers too. This named-limiter mode never raises — it returns the response
        directly, so it (unlike the plain mode above) needs no exception-header plumbing.
    """

    def __init__(
        self,
        max_attempts: int = 60,
        decay_seconds: int = 60,
        *,
        name: str = "default",
        cache: Any = None,
        limiter_name: str | None = None,
    ) -> None:
        self.max_attempts = max_attempts
        self.decay_seconds = decay_seconds
        self.name = name
        self._cache = cache  # CacheRepository for distributed limiting; None → in-process
        self._limiter_name = limiter_name

    def _client(self, request: Any) -> str:
        getter = getattr(request, "ip", None)
        client: Any = getter() if callable(getter) else None
        return str(client) if client else "global"

    async def _hit(self, key: str) -> int:
        """Increment the window counter for ``key`` and return the new count."""
        if self._cache is not None:  # distributed: atomic incr in the cache, TTL on first hit
            count = await self._cache.increment(key)
            if count == 1:
                await self._cache.expire(key, self.decay_seconds)
            return int(count)
        import time

        now = time.monotonic()
        count, start = _THROTTLE_HITS.get(key, (0, now))
        if now - start >= self.decay_seconds:
            count, start = 0, now
        count += 1
        _THROTTLE_HITS[key] = (count, start)
        return count

    async def handle(self, request: Request, call_next: Callable[[Request], Awaitable[Any]]) -> Any:
        if self._limiter_name is not None:
            return await self._handle_named(request, call_next)
        key = f"{self.name}:{self._client(request)}"
        count = await self._hit(key)
        if count > self.max_attempts:
            await self._plain_over_limit(key)  # raises HttpException(429) with rate-limit headers
        _RATE_LIMIT_HEADERS.set(
            {
                "X-RateLimit-Limit": str(self.max_attempts),
                "X-RateLimit-Remaining": str(max(self.max_attempts - count, 0)),
            }
        )
        return await call_next(request)

    async def _retry_after(self, key: str) -> int:
        """Seconds until this window resets. Exact for the in-process store; for the distributed
        cache we bound it by the decay window (the key's TTL guarantees a reset within it)."""
        if self._cache is not None:
            return self.decay_seconds
        import time

        entry = _THROTTLE_HITS.get(key)
        if entry is None:
            return self.decay_seconds
        _, start = entry
        return max(int(start + self.decay_seconds - time.monotonic()), 0)

    async def _plain_over_limit(self, key: str) -> Any:
        import time

        from arvel.http.exceptions import HttpException
        from arvel.localization import trans

        retry_after = await self._retry_after(key)
        raise HttpException(
            429,
            trans("http.too_many_requests"),
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(self.max_attempts),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(time.time()) + retry_after),
            },
        )

    async def _handle_named(self, request: Any, call_next: Any) -> Any:
        from arvel.kernel import app, has_application

        if not has_application() or not app().bound("limiter"):
            raise RuntimeError(
                f"throttle:{self._limiter_name} — no `limiter` bound (needs a cache-backed app)."
            )
        limiter = app().make("limiter")
        resolver = limiter.limiter(self._limiter_name)
        if resolver is None:
            raise RuntimeError(
                f"Unknown rate limiter {self._limiter_name!r} — register it with "
                f"RateLimiter.for_({self._limiter_name!r}, resolver)."
            )
        resolved: Limit | list[Limit] | None = resolver(request)
        if inspect.isawaitable(resolved):
            resolved = await resolved
        if resolved is None:  # the resolver opted this request out — unlimited
            return await call_next(request)
        limits: list[Limit] = resolved if isinstance(resolved, list) else [resolved]

        remaining = 0
        for limit in limits:
            key = f"{self._limiter_name}:{limit.decay_seconds}:{limit.key or _default_segment(request)}"
            attempts_before = await limiter.attempts(key)
            if attempts_before >= limit.max_attempts:
                retry_after = await limiter.available_in(key)
                return await self._too_many_attempts_response(request, limit, retry_after)
            await limiter.hit(key, limit.decay_seconds)
            remaining = max(limit.max_attempts - attempts_before - 1, 0)

        _RATE_LIMIT_HEADERS.set(
            {
                "X-RateLimit-Limit": str(limits[-1].max_attempts),
                "X-RateLimit-Remaining": str(max(remaining, 0)),
            }
        )
        return await call_next(request)

    @staticmethod
    async def _too_many_attempts_response(request: Any, limit: Limit, retry_after: int) -> Any:
        if limit.response_callback is not None:
            result = limit.response_callback(request)
            if inspect.isawaitable(result):
                result = await result
            return result
        import time

        from arvel.http.response import Response
        from arvel.localization import trans

        return Response(
            {"message": trans("http.too_many_requests")},
            status=429,
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(limit.max_attempts),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(time.time()) + retry_after),
            },
        )

    async def terminate(self, request: Any, response: Any) -> None:
        success_headers = _RATE_LIMIT_HEADERS.get()
        if success_headers is None:
            return
        headers: dict[str, str] | None = getattr(response, "headers", None)
        if isinstance(headers, dict):
            headers.update(success_headers)


class StartSession(Middleware):
    """Attach a mutable ``request.session`` dict loaded from (and persisted to) a store keyed
    by the session cookie (web group). A missing cookie starts a fresh session. The default
    store is in-process; pass a ``cache`` (a ``CacheRepository``) to persist sessions over a
    shared backend (e.g. Redis) so they survive across processes/hosts.

    The cookie is ``HttpOnly`` + ``SameSite=Lax`` + ``Secure`` (by default) and, when Secure, carries
    the ``__Host-`` prefix (``__Host-session``) — which browsers only accept with ``Secure`` + ``Path=/``
    + no ``Domain``, closing cookie-injection from a sibling subdomain. On plain-HTTP dev (``secure=False``)
    the name falls back to ``session`` (browsers reject ``__Host-`` without Secure).

    **Cookie emission is success-path only.** The rotated/new cookie is set in ``terminate``, which the
    kernel runs after a response is built; if a handler *raises*, the kernel renders the error response
    outside ``terminate`` so no ``Set-Cookie`` is emitted. This is fail-closed — ``handle``'s teardown
    has already forgotten the old session id server-side, so the client simply starts a fresh session
    on its next request (it never keeps a live old id). A clean logout/login that 500s mid-flight
    therefore just desyncs the cookie, never leaks a session."""

    def __init__(
        self,
        store: dict[str, dict[str, Any]] | None = None,
        *,
        cache: Any = None,
        lifetime: int | None = None,  # MINUTES; converted to seconds below
        secure: bool | None = None,
        host_prefix: bool | None = None,
    ) -> None:
        settings = SessionSettings()
        self._store = store if store is not None else _SESSIONS
        self._cache = cache  # CacheRepository for distributed sessions; None → in-process dict
        # precedence: explicit arg > session.* config > built-in default
        minutes = lifetime if lifetime is not None else settings.lifetime
        self._max_age = minutes * 60
        self._secure = (  # mark the cookie Secure (HTTPS-only); set False for plain-HTTP dev
            secure if secure is not None else settings.secure
        )
        # __Host- prefix defaults on whenever the cookie is Secure (browsers require Secure for it)
        host_prefix = host_prefix if host_prefix is not None else settings.host_prefix
        use_prefix = host_prefix if host_prefix is not None else self._secure
        self._cookie_name = "__Host-session" if (use_prefix and self._secure) else "session"

    def _cookie_sid(self, request: Any) -> str | None:
        getter = getattr(request, "cookie", None)
        sid = getter(self._cookie_name) if callable(getter) else None
        return str(sid) if sid else None

    async def _load(self, sid: str) -> dict[str, Any]:
        if self._cache is not None:
            loaded: Any = await self._cache.get(f"session:{sid}")
            if isinstance(loaded, dict):
                return dict(cast("dict[str, Any]", loaded))  # copy, so it doesn't alias the cache
            return {}
        return self._store.setdefault(sid, {})

    async def _save(self, sid: str, session: dict[str, Any]) -> None:
        if self._cache is not None:
            await self._cache.put(f"session:{sid}", session, ttl=self._max_age)
        else:
            self._store[sid] = session

    async def _forget(self, sid: str) -> None:
        if self._cache is not None:
            await self._cache.forget(f"session:{sid}")
        else:
            self._store.pop(sid, None)

    async def handle(self, request: Request, call_next: Callable[[Request], Awaitable[Any]]) -> Any:
        import secrets

        cookie_sid = self._cookie_sid(request)
        sid = cookie_sid or secrets.token_hex(16)
        session = await self._load(sid)
        request.session = session  # mutated by handlers; persisted on the way out
        from arvel.http.flash import FlashBag

        FlashBag(session).age()  # expire last-request flashes/errors (one-request lifecycle)
        # the underscore-prefixed attrs below are a documented cross-module contract with
        # arvel.http.session (regenerate_session/invalidate_session mutate the same names), not an
        # encapsulation leak — pyright's privacy check doesn't know that, hence the ignores.
        request._session_id = sid  # pyright: ignore[reportPrivateUsage]
        drop: set[str] = set()  # old ids to forget (regenerate/invalidate add to this same set)
        request._session_drop = drop  # pyright: ignore[reportPrivateUsage]
        request._session_set_cookie = cookie_sid is None  # pyright: ignore[reportPrivateUsage]
        # stash for the kernel's after_response persist: flash/errors/old-input are written to
        # request.session AFTER this pipeline unwinds (redirect + exception-render both run later),
        # and a serializing store snapshots on save — so the finally-save below would miss them.
        state = getattr(getattr(request, "raw", None), "state", None)
        if state is not None:
            state.arvel_session = (self, request)
        try:
            return await call_next(request)
        finally:
            await self.persist(request)

    async def persist(self, request: Any) -> None:
        """Persist request.session to its store and forget any dropped ids. Idempotent — the
        pipeline calls it on the way out, and the kernel calls it again after the response is
        built so late-written flash on a serializing (cache) store isn't lost."""
        for old in getattr(request, "_session_drop", ()) or ():
            await self._forget(old)
        request._session_drop = set()  # pyright: ignore[reportPrivateUsage]
        sid = getattr(request, "_session_id", None)
        if sid is not None:
            await self._save(sid, request.session)

    async def terminate(self, request: Any, response: Any) -> None:
        if not getattr(request, "_session_set_cookie", False):
            return
        setter = getattr(response, "set_cookie", None)
        if callable(setter):
            setter(
                self._cookie_name,
                request._session_id,
                max_age=self._max_age,
                path="/",
                httponly=True,
                secure=self._secure,
                samesite="lax",
            )


class ValidateCsrfToken(Middleware):
    """Reject state-changing requests whose CSRF token doesn't match the session (web group).

    Safe methods (GET/HEAD/OPTIONS) are exempt. Two gates apply to the rest, and both must pass:

    **Provenance.** A request carrying an ``Origin`` header (browsers send it on cross-origin and
    most same-origin unsafe requests) must originate from the request's own host or a configured
    ``session.trusted_origins`` entry; ``Referer`` is the fallback signal when ``Origin`` is
    absent. A request with neither header (curl, native API clients) is judged by the token alone
    — provenance can only be checked when the client asserts it.

    **Token.** The submitted token comes from the ``X-CSRF-TOKEN``
    (or ``X-XSRF-TOKEN``) header, or the ``_token`` field of a form/JSON body; the expected
    token is the session's ``_token`` (seeded by this middleware on each web request, so the form can
    render + submit it). A mismatch (or a missing token) raises a 419 ``ValidationException`` ('s
    page-expired status).

    On the way out it mirrors the token into a **JS-readable ``XSRF-TOKEN`` cookie**
    so a decoupled SPA can read it and echo it back as ``X-XSRF-TOKEN`` — no server-rendered meta tag
    needed. That cookie is intentionally **not** ``HttpOnly`` (it's the double-submit token, not a
    secret — the session id cookie stays ``HttpOnly``); it inherits the session's Secure flag.

    ``except_`` exempts URI glob patterns from CSRF entirely — e.g. a webhook
    endpoint a third party posts to with no session/token. Override the ``except_`` class attribute
    in a subclass, and/or configure ``session.csrf_except`` (both apply — merged, not replaced).
    Patterns are matched via ``request.is_()`` (``fnmatch`` against the path with no leading slash).
    """

    SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
    HEADER = "x-csrf-token"
    COOKIE = "XSRF-TOKEN"
    #: URI glob patterns exempt from CSRF — override in a subclass; merged
    #: with ``config('session.csrf_except')`` at construction.
    except_: ClassVar[list[str]] = []

    def __init__(self) -> None:
        settings = SessionSettings()  # share the session cookie's Secure flag + lifetime
        self._secure = settings.secure
        self._max_age = settings.lifetime * 60  # minutes -> seconds for max-age
        self._except = [*self.except_, *settings.csrf_except]
        self._trusted = list(settings.trusted_origins)

    def _is_excepted(self, request: Any) -> bool:
        checker = getattr(request, "is_", None)
        return callable(checker) and any(checker(pattern) for pattern in self._except)

    async def _submitted(self, request: Any) -> Any:
        header = request.header(self.HEADER) or request.header("x-xsrf-token")
        if header:
            return header
        # fall back to the body's `_token` field — HTML form (csrf_field()) or JSON
        content_type = request.header("content-type") or ""
        try:
            data = (
                await request.form()
                if ("form" in content_type or "urlencoded" in content_type)
                else await request.json()
            )
        except Exception:  # unparseable/absent body → no token
            return None
        return data.get("_token") if hasattr(data, "get") else None

    def _expected(self, request: Any) -> Any:
        session = getattr(request, "session", None)
        if not isinstance(session, dict):
            return None
        return cast("dict[str, Any]", session).get("_token")

    def _asserted_origin(self, request: Any) -> str | None:
        """The origin the client asserts: the ``Origin`` header, else one derived from
        ``Referer``. ``None`` when the client asserts nothing (token-only fallback)."""
        origin = request.header("origin")
        if origin:
            return str(origin)
        referer = request.header("referer")
        if referer:
            from urllib.parse import urlsplit

            parts = urlsplit(str(referer))
            if parts.scheme and parts.netloc:
                return f"{parts.scheme}://{parts.netloc}"
            return "null"  # an unparseable referer asserts provenance but proves none
        return None

    def _origin_ok(self, request: Any, origin: str) -> bool:
        from urllib.parse import urlsplit

        if origin == "null":  # sandboxed iframe / data: URL — provenance explicitly withheld
            return False
        parts = urlsplit(origin)
        host = parts.hostname
        if host is None:
            return False
        own = getattr(request, "host", None)
        own_host = str(own() or "") if callable(own) else ""
        if own_host.lower() == host:  # urlsplit lowercases hostname; Host header may not be
            return True
        for entry in self._trusted:
            if "://" in entry:
                # an Origin value is scheme://host[:port] — lowercasing the whole string is
                # safe (no path/userinfo) and matches how urlsplit folds the hostname
                if origin.lower() == entry.lower():
                    return True
            elif entry.lower() == host:  # bare host: any scheme/port
                return True
        return False

    async def handle(self, request: Request, call_next: Callable[[Request], Awaitable[Any]]) -> Any:
        import secrets

        session = getattr(request, "session", None)
        if isinstance(session, dict):  # ensure a token exists so forms can render + submit it
            cast("dict[str, Any]", session).setdefault("_token", secrets.token_hex(32))
        if request.method().upper() in self.SAFE_METHODS or self._is_excepted(request):
            return await call_next(request)
        asserted = self._asserted_origin(request)
        if asserted is not None and not self._origin_ok(request, asserted):
            from arvel.localization import trans
            from arvel.validation import ValidationException

            raise ValidationException(trans("http.csrf"), status=419)
        expected = self._expected(request)
        submitted = await self._submitted(request)
        # constant-time compare (must not leak the secret via timing); bytes so a non-ASCII
        # header yields a clean 419 instead of a 500 (compare_digest rejects non-ASCII str)
        if (
            not isinstance(expected, str)
            or not expected
            or not isinstance(submitted, str)
            or not secrets.compare_digest(submitted.encode(), expected.encode())
        ):
            from arvel.localization import trans
            from arvel.validation import ValidationException

            raise ValidationException(trans("http.csrf"), status=419)
        return await call_next(request)

    async def terminate(self, request: Any, response: Any) -> None:
        """Expose the session token as a readable ``XSRF-TOKEN`` cookie so a decoupled SPA (no
        server-rendered meta tag) can read it and send it back as ``X-XSRF-TOKEN``.
        Not ``HttpOnly`` (JS must read it); inherits the session's Secure flag; ``SameSite=Lax``."""
        session = getattr(request, "session", None)
        token = cast("dict[str, Any]", session).get("_token") if isinstance(session, dict) else None
        setter = getattr(response, "set_cookie", None)
        if token and callable(setter):
            setter(
                self.COOKIE,
                token,
                max_age=self._max_age,
                path="/",
                httponly=False,  # the SPA's JS must read this to echo it back in the header
                secure=self._secure,
                samesite="lax",
            )


class AuthenticateMiddleware(Middleware):
    """Resolve the request's user via the app's ``user_resolver`` binding and bind it to
    ``arvel.auth.current_user`` for the request's duration (cleared afterward)."""

    async def handle(self, request: Request, call_next: Callable[[Request], Awaitable[Any]]) -> Any:
        import inspect

        from arvel.kernel import app, has_application
        from arvel.support import current_user

        user = None
        if has_application() and app().bound("user_resolver"):
            resolved = app().make("user_resolver")(request)
            user = await resolved if inspect.isawaitable(resolved) else resolved
        token = current_user.set(user)
        try:
            return await call_next(request)
        finally:
            current_user.reset(token)


class RequestContextMiddleware(Middleware):
    """Bind a unique request id into the log context for the request's duration.

    Honours an incoming ``X-Request-ID`` header, otherwise generates one. Every log
    event emitted while handling the request then carries ``request_id`` automatically.
    """

    async def handle(self, request: Request, call_next: Callable[[Request], Awaitable[Any]]) -> Any:
        import uuid

        from arvel.kernel.logging import LogManager

        incoming = request.header("x-request-id") if hasattr(request, "header") else None
        request_id = incoming or uuid.uuid7().hex
        LogManager.with_context(request_id=request_id)
        try:
            return await call_next(request)
        finally:
            LogManager.clear_context()


class LocaleMiddleware(Middleware):
    """Set the request locale for the call's duration. Precedence: the authenticated user's
    preferred locale, then the ``Accept-Language`` header (doc 21)."""

    async def handle(self, request: Request, call_next: Callable[[Request], Awaitable[Any]]) -> Any:
        from arvel.localization import current_locale

        locale = self._from_user() or self._from_header(request)
        if not locale:
            return await call_next(request)
        token = current_locale.set(locale)
        try:
            return await call_next(request)
        finally:
            current_locale.reset(token)

    @staticmethod
    def _from_user() -> str | None:
        from arvel.support import current_user

        user = current_user.get()
        if user is None:
            return None
        pref = getattr(user, "locale", None) or getattr(user, "preferred_locale", None)
        return str(pref) if pref else None

    @staticmethod
    def _from_header(request: Any) -> str | None:
        header = request.header("accept-language") if hasattr(request, "header") else None
        if not header:
            return None
        return str(header).split(",")[0].split("-")[0].strip()


class ValidatePostSize(Middleware):
    """Reject an over-large request body with **413** before the handler runs (``ValidatePostSize``). The limit is ``config('app.max_request_size')`` bytes (default 10 MiB);
    pass ``max_bytes`` to override. A missing/invalid ``Content-Length`` is not enforced here
    (chunked/streamed bodies are bounded by the ASGI server)."""

    DEFAULT_MAX = 10 * 1024 * 1024  # 10 MiB

    def __init__(self, max_bytes: int | None = None) -> None:
        self.max_bytes = max_bytes

    def _limit(self) -> int:
        if self.max_bytes is not None:
            return self.max_bytes
        from arvel.kernel import app, has_application

        if has_application() and app().bound("config"):
            return int(app("config").get("app.max_request_size", self.DEFAULT_MAX))
        return self.DEFAULT_MAX

    async def handle(self, request: Request, call_next: Callable[[Request], Awaitable[Any]]) -> Any:
        length = request.header("content-length")
        if length is not None:
            try:
                too_large = int(length) > self._limit()
            except ValueError:
                too_large = False
            if too_large:
                from arvel.http.response import Response

                return Response({"message": "Payload too large."}, status=413)
        return await call_next(request)


class ValidateHost(Middleware):
    """Reject a request whose Host is not in ``config('app.trusted_hosts')`` with **400**. When the list is unset/empty all hosts
    are allowed, so this is a no-op until an app opts in."""

    async def handle(self, request: Request, call_next: Callable[[Request], Awaitable[Any]]) -> Any:
        from arvel.kernel import app, has_application

        allowed: Any = None
        if has_application() and app().bound("config"):
            allowed = app("config").get("app.trusted_hosts")
        if isinstance(allowed, (list, tuple)) and allowed and request.host() not in allowed:
            from arvel.http.response import Response

            return Response({"message": "Invalid host header."}, status=400)
        return await call_next(request)


class ShareErrorsFromSession(Middleware):
    """Share session-flashed data as view globals on every request: the validation ``errors`` bag
    and the ``old`` callable for form repopulation. Web group, runs after ``StartSession`` (which sets ``request.session`` and
       ages the flash). No-op when no session or view is bound, so non-view apps are unaffected."""

    async def handle(self, request: Request, call_next: Callable[[Request], Awaitable[Any]]) -> Any:
        from arvel.kernel import app, has_application

        session = getattr(request, "session", None)
        if isinstance(session, dict) and has_application() and app().bound("view"):
            from arvel.http.flash import FlashBag

            bag = FlashBag(cast("dict[str, Any]", session))
            app("view").share(errors=bag.errors(), old=bag.old)
        return await call_next(request)


class ValidateSignature(Middleware):
    """the ``signed`` middleware: reject (**403**) a request whose URL lacks a valid signature.

    Pair it with:meth:`arvel.routing.Router.signed_url` (``Route.signed_url(name,...)``): the
    signature is an itsdangerous MAC over the route's path+query (plus an optional ``expires`` unix
    timestamp), and the signing key defaults to the app key. Apply per route, e.g.
    ``Route.get("/unsubscribe/{id}", handler).middleware(ValidateSignature)``. A tampered or expired
    URL gets a 403 before the handler runs."""

    async def handle(self, request: Request, call_next: Callable[[Request], Awaitable[Any]]) -> Any:
        from arvel.kernel import app, has_application

        raw_url = getattr(getattr(request, "raw", None), "url", None)
        url = str(getattr(raw_url, "path", "") or request.path())
        query = str(getattr(raw_url, "query", "") or "")
        if query:
            url += "?" + query
        valid = (
            has_application() and app().bound("router") and app("router").has_valid_signature(url)
        )
        if not valid:
            from arvel.http.response import Response

            return Response({"message": "Invalid signature."}, status=403)
        return await call_next(request)


def _multipart_field(ctype: str, body: bytes, field: str) -> str:
    """Pull one text field's value out of a ``multipart/form-data`` body without fully parsing it
    (used only to read ``_method``). Returns "" if the boundary/field isn't found."""
    marker = "boundary="
    at = ctype.find(marker)
    if at == -1:
        return ""
    boundary = ctype[at + len(marker) :].split(";")[0].strip().strip('"')
    delimiter = b"--" + boundary.encode("latin-1")
    needle = f'name="{field}"'.encode("latin-1")  # the closing quote disambiguates "_method2" etc.
    for part in body.split(delimiter):
        if needle not in part:
            continue
        sep = part.find(b"\r\n\r\n")
        if sep != -1:
            return part[sep + 4 :].rstrip(b"\r\n").decode("latin-1", "ignore")
    return ""


def _form_method_override(ctype: str, body: bytes) -> str:
    """The ``_method`` value from a form body (urlencoded or multipart), uppercased; "" if absent."""
    from urllib.parse import parse_qs

    if ctype.startswith("application/x-www-form-urlencoded"):
        return (parse_qs(body.decode("latin-1")).get("_method") or [""])[0].upper()
    if ctype.startswith("multipart/form-data"):
        return _multipart_field(ctype, body, "_method").upper()
    return ""


class MethodOverride:
    """ASGI middleware for HTML form method-spoofing: a POST whose form body
    carries ``_method=PUT|PATCH|DELETE`` is **routed as that method**.

    It runs at the ASGI layer — *before* the router matches by HTTP method — so it rewrites
    ``scope["method"]`` and replays the buffered body downstream (HTML forms can only GET/POST, so
    this is how a ``<form method=post>`` reaches a PUT/PATCH/DELETE route). Both
    ``application/x-www-form-urlencoded`` and ``multipart/form-data`` (file-upload) bodies are
    inspected; everything else passes through untouched. Pair with the ``method_field()`` view global."""

    _SPOOFABLE = frozenset({"PUT", "PATCH", "DELETE"})
    _FORM_TYPES = ("application/x-www-form-urlencoded", "multipart/form-data")

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or scope.get("method") != "POST":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        ctype = headers.get(b"content-type", b"").decode("latin-1").lower()
        if not ctype.startswith(self._FORM_TYPES):
            await self.app(scope, receive, send)
            return

        # buffer the request body so we can read _method, then replay it untouched downstream
        buffered: list[Any] = []
        body = b""
        more = True
        while more:
            message = await receive()
            buffered.append(message)
            if message["type"] == "http.request":
                body += message.get("body", b"")
                more = message.get("more_body", False)
            else:
                more = False

        override = _form_method_override(ctype, body)
        if override in self._SPOOFABLE:
            scope = {**scope, "method": override}

        async def replay() -> Any:
            return buffered.pop(0) if buffered else await receive()

        await self.app(scope, replay, send)
