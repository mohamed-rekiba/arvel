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


# per-request rate-limit headers to attach to an allowed response — a ContextVar (not instance
# state) because a throttle middleware instance is shared across concurrent requests.
_RATE_LIMIT_HEADERS: ContextVar[dict[str, str] | None] = ContextVar(
    "arvel_rate_limit_headers", default=None
)
# Default in-process session store (session id -> data). Apps swap in a cache-backed store.
_SESSIONS: dict[str, dict[str, Any]] = {}

# H14: the process-global fallback window for a cache-less plain ``ThrottleRequests`` — the
# array-cache-backed counterpart to the old monotonic dict (DR-0041). Rebuilt lazily so it needs
# no app/config; dropping the reference (see `reset_rate_limiter`) is how it's cleared.
_default_limiter_cache: Any = None


def _default_limiter() -> Any:
    global _default_limiter_cache
    if _default_limiter_cache is None:
        from arvel.cache import CacheManager
        from arvel.http.rate_limiter import RateLimiter

        _default_limiter_cache = RateLimiter(CacheManager().create_array_driver())
    return _default_limiter_cache


def reset_rate_limiter() -> None:
    """Clear the in-process rate-limiter window state.

    The default ``ThrottleRequests`` state is **process-global** — correct for one running app, but
    it leaks across the multiple app instances a test suite builds in a single process, so the api
    throttle eventually 429s spuriously mid-suite. Call this between tests (an autouse fixture) to
    isolate each test. No effect on a cache-backed (distributed) limiter — clear that store instead.

    H14: retargeted from the old monotonic dict's ``.clear()`` to dropping the process-global
    array-cache limiter — the next use lazily rebuilds a fresh, empty one.
    """
    global _default_limiter_cache
    _default_limiter_cache = None


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

    By default state lives in the process-global array-cache limiter (:func:`_default_limiter`).
    Pass a ``cache`` (a ``CacheRepository``) to count over a shared backend instead — that makes
    limiting **distributed** across processes/hosts (e.g. Redis).

    Pass ``limiter_name`` instead (what the ``throttle:<name>`` route-middleware string builds,
    e.g. ``Route.get(...).middleware("throttle:api")``) to rate-limit via a **named limiter**
    registered on the app's ``limiter`` (:class:`~arvel.http.rate_limiter.RateLimiter`) with
    ``RateLimiter.for_(name, resolver)``: ``resolver(request)`` returns a
    :class:`~arvel.http.rate_limiter.Limit`, a ``list[Limit]``, or ``None`` (unlimited).

    Both modes count through the same fixed-window ``RateLimiter`` (DR-0041 — H14) and share ONE
    429 decision: a limit's own ``.response(cb)`` builder wins when set; otherwise
    ``HttpException(429)`` is raised carrying ``Retry-After``/``X-RateLimit-Limit``/
    ``X-RateLimit-Remaining``/``X-RateLimit-Reset``, so ``render_exception`` content-negotiates the
    body exactly like every other framework error (422/403/404/…). A limit with no explicit
    ``.by(key)`` segments by :func:`_default_segment` (user id, else IP). A successful response
    carries the ``X-RateLimit-*`` headers too (applied in :meth:`terminate`).
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
        self._cache = cache  # CacheRepository for distributed limiting; None → process-global array
        self._limiter_name = limiter_name

    def _plain_limiter(self) -> Any:
        """The ``RateLimiter`` a cache-less plain instance counts through: an explicit ``cache=``
        wraps directly; otherwise the process-global array-cache default (DR-0041)."""
        from arvel.http.rate_limiter import RateLimiter

        if self._cache is not None:
            return RateLimiter(self._cache)
        return _default_limiter()

    async def _resolve_named(self, request: Any) -> list[Limit] | None:
        """The named-limiter's registered resolver: a ``Limit``/``list[Limit]``/``None`` (opts this
        request out — unlimited)."""
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
        if resolved is None:
            return None
        return resolved if isinstance(resolved, list) else [resolved]

    async def handle(self, request: Request, call_next: Callable[[Request], Awaitable[Any]]) -> Any:
        from arvel.http.rate_limiter import Limit

        limits: list[Limit]
        if self._limiter_name is not None:
            from arvel.kernel import app

            resolved = await self._resolve_named(request)
            if resolved is None:  # the resolver opted this request out — unlimited
                return await call_next(request)
            limits = resolved
            limiter = app().make("limiter")
            scope = self._limiter_name
        else:
            limiter = self._plain_limiter()
            limits = [Limit(self.max_attempts, self.decay_seconds)]
            scope = self.name

        remaining = 0
        for limit in limits:
            key = f"{scope}:{limit.decay_seconds}:{limit.key or _default_segment(request)}"
            # atomic increment-then-compare (not attempts()-then-hit()): two concurrent requests
            # both reading "under limit" before either increments would let more than
            # max_attempts through — increment_with_ttl folds the check into the same atomic op.
            count = await limiter.hit_with_ttl(key, limit.decay_seconds)
            if count > limit.max_attempts:
                retry_after = await limiter.available_in(key)
                return await self._over_limit(request, limit, retry_after)
            remaining = max(limit.max_attempts - count, 0)

        _RATE_LIMIT_HEADERS.set(
            {
                "X-RateLimit-Limit": str(limits[-1].max_attempts),
                "X-RateLimit-Remaining": str(remaining),
            }
        )
        return await call_next(request)

    @staticmethod
    async def _over_limit(request: Any, limit: Limit, retry_after: int) -> Any:
        """The one 429 decision both modes share (DR-0041): a custom ``Limit.response(callback)``
        wins; otherwise raise ``HttpException(429)`` carrying the rate-limit headers so
        ``render_exception`` content-negotiates the body like every other framework error."""
        if limit.response_callback is not None:
            result = limit.response_callback(request)
            if inspect.isawaitable(result):
                result = await result
            return result
        import time

        from arvel.http.exceptions import HttpException
        from arvel.localization import trans

        raise HttpException(
            429,
            trans("http.too_many_requests"),
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


#: Input-normalization recursion ceiling — a 2-bytes-per-level hostile body fits under
#: ValidatePostSize yet nests thousands deep; real payloads never approach this.
_TRANSFORM_MAX_DEPTH = 64


class TrimStrings(Middleware):
    """Strip leading/trailing whitespace from every string in the parsed input, recursively
    through nested dicts/lists (H8) — global, default-on.

    ``except_`` names are matched on the dict **key**, at any nesting depth: a key in the set is
    left completely untouched (its subtree isn't recursed into either), so a password field
    reaches validation exactly as typed."""

    except_: ClassVar[tuple[str, ...]] = ("password", "password_confirmation", "current_password")

    def _transform(self, value: Any, _depth: int = 0) -> Any:
        # normalization is a convenience, not a boundary — a hostile deeply-nested
        # subtree is left as-is rather than recursed into a RecursionError 500
        if _depth > _TRANSFORM_MAX_DEPTH:
            return value
        if isinstance(value, dict):
            return {
                k: (v if k in self.except_ else self._transform(v, _depth + 1))
                for k, v in cast("dict[Any, Any]", value).items()
            }
        if isinstance(value, list):
            return [self._transform(v, _depth + 1) for v in cast("list[Any]", value)]
        if isinstance(value, str):
            return value.strip()
        return value

    async def handle(self, request: Request, call_next: Callable[[Request], Awaitable[Any]]) -> Any:
        request._input_transforms.append(self._transform)  # pyright: ignore[reportPrivateUsage]
        return await call_next(request)


class ConvertEmptyStringsToNull(Middleware):
    """Convert every ``""`` in the parsed input to ``None``, recursively through nested
    dicts/lists (H8) — global, default-on, runs after :class:`TrimStrings`.

    This flips validation outcomes: a ``nullable`` field submitted as ``""`` now passes (treated
    as absent), and a ``required`` field submitted as ``""`` now fails (an empty string no longer
    counts as "provided"). Unlike :class:`TrimStrings` there is no password exception — an
    empty password becomes ``None`` and fails ``required`` either way."""

    def _transform(self, value: Any, _depth: int = 0) -> Any:
        if _depth > _TRANSFORM_MAX_DEPTH:
            return value  # same ceiling as TrimStrings — never recurse into a 500
        if isinstance(value, dict):
            return {
                k: self._transform(v, _depth + 1) for k, v in cast("dict[Any, Any]", value).items()
            }
        if isinstance(value, list):
            return [self._transform(v, _depth + 1) for v in cast("list[Any]", value)]
        return None if value == "" else value

    async def handle(self, request: Request, call_next: Callable[[Request], Awaitable[Any]]) -> Any:
        request._input_transforms.append(self._transform)  # pyright: ignore[reportPrivateUsage]
        return await call_next(request)


class EncryptCookies(Middleware):
    """Encrypt every outgoing/incoming cookie by default (H7 — first in the web group): a cookie
    value at rest in the browser is otherwise plaintext even though it's meant to be opaque
    server state.

    The CSRF double-submit cookie (``XSRF-TOKEN``) is deliberately excepted — it is **not** a
    secret by design (a decoupled SPA's JS must read it to echo it back as a header), so
    encrypting it would break the double-submit pattern while protecting nothing.

    Resolves the app's bound ``encrypter`` (:class:`~arvel.security.Encrypter`) and stashes a
    codec — ``(encrypt, decrypt, except_names)`` — on the request for :meth:`Request.cookie`
    (reads) and :func:`emit_cookie` (writes) to consult. When no app is running, no encrypter is
    bound, or ``config('app.key')`` isn't set (the encrypter would fail to construct), nothing is
    stashed and cookies stay plaintext — encryption is opt-in via having a configured app, not a
    hard requirement."""

    except_: ClassVar[tuple[str, ...]] = ("XSRF-TOKEN",)

    async def handle(self, request: Request, call_next: Callable[[Request], Awaitable[Any]]) -> Any:
        from arvel.kernel import app, has_application

        if has_application() and app().bound("encrypter") and app().config("app.key"):
            encrypter = app().make("encrypter")
            request._cookie_codec = (  # pyright: ignore[reportPrivateUsage]
                encrypter.encrypt_string,
                encrypter.decrypt_string,
                self.except_,
            )
        return await call_next(request)


def emit_cookie(request: Any, response: Any, name: str, value: str, **attrs: Any) -> None:
    """The one write path for every Set-Cookie (H7): encrypts ``value`` through ``request``'s
    cookie codec (stashed by :class:`EncryptCookies`) unless ``name`` is excepted or no codec is
    active, then delegates to ``response.set_cookie``. Every cookie-emitting call site
    (``StartSession.terminate``, the CSRF ``XSRF-TOKEN`` mirror, the kernel's queued-cookie apply)
    routes through here, so encrypt-or-not is one decision, not three."""
    codec = getattr(request, "_cookie_codec", None)
    if codec is not None:
        encrypt, _decrypt, except_names = codec
        if name not in except_names:
            value = encrypt(value)
    setter = getattr(response, "set_cookie", None)
    if callable(setter):
        setter(name, value, **attrs)


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
        emit_cookie(
            request,
            response,
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
            from arvel.http.exceptions import HttpException
            from arvel.localization import trans

            raise HttpException(419, trans("http.csrf"))
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
            from arvel.http.exceptions import HttpException
            from arvel.localization import trans

            raise HttpException(419, trans("http.csrf"))
        return await call_next(request)

    async def terminate(self, request: Any, response: Any) -> None:
        """Expose the session token as a readable ``XSRF-TOKEN`` cookie so a decoupled SPA (no
        server-rendered meta tag) can read it and send it back as ``X-XSRF-TOKEN``.
        Not ``HttpOnly`` (JS must read it); inherits the session's Secure flag; ``SameSite=Lax``."""
        session = getattr(request, "session", None)
        token = cast("dict[str, Any]", session).get("_token") if isinstance(session, dict) else None
        if token:
            emit_cookie(
                request,
                response,
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
    ``arvel.auth.current_user`` for the request's duration (cleared afterward).

    Also applies the resolved user's preferred locale (doc 21): ``LocaleMiddleware`` runs
    as an early global — before any authentication — so the user-pref branch of its precedence can
    only hold if the middleware that *learns* the user applies the preference. It does so **only when
    the request carries no explicit switch** (``?lang=`` / a ``locale`` cookie), so an active choice
    always outranks the stored preference, which in turn outranks ``Accept-Language``."""

    async def handle(self, request: Request, call_next: Callable[[Request], Awaitable[Any]]) -> Any:
        import inspect

        from arvel.kernel import app, has_application
        from arvel.support import current_user

        user = None
        if has_application() and app().bound("user_resolver"):
            resolved = app().make("user_resolver")(request)
            user = await resolved if inspect.isawaitable(resolved) else resolved
        token = current_user.set(user)
        locale_token = None
        # Stored preference applies only when the request carries no explicit switch — an active
        # ?lang=/locale-cookie choice outranks the user's saved locale.
        pref = (
            None
            if LocaleMiddleware.explicit_locale(request)
            else LocaleMiddleware.user_preferred_locale()  # reads the user just bound above
        )
        if pref:
            from arvel.localization import current_locale

            locale_token = current_locale.set(pref)
        try:
            return await call_next(request)
        finally:
            if locale_token is not None:
                from arvel.localization import current_locale

                current_locale.reset(locale_token)
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
    """Set the request locale for the call's duration. Precedence:
    an **explicit switch** (``?lang=``/``?locale=`` query param or a ``locale`` cookie), then the
    authenticated **user's stored preference**, then the ``Accept-Language`` header.

    Under the shipped wiring this middleware runs BEFORE authentication, so the user-preference
    branch only fires in standalone/custom wiring — ``AuthenticateMiddleware`` applies the stored
    preference in a real app (it calls :meth:`user_preferred_locale` after resolving the user, but
    only when no explicit switch is present, so an active choice always wins)."""

    async def handle(self, request: Request, call_next: Callable[[Request], Awaitable[Any]]) -> Any:
        from arvel.localization import current_locale

        # user_preferred_locale() is None under real wiring (the kernel resets current_user
        # before this runs); AuthenticateMiddleware delivers the user-pref precedence there.
        locale = (
            self.explicit_locale(request)
            or self.user_preferred_locale()
            or self._from_header(request)
        )
        if not locale:
            return await call_next(request)
        token = current_locale.set(locale)
        try:
            return await call_next(request)
        finally:
            current_locale.reset(token)

    @staticmethod
    def explicit_locale(request: Any) -> str | None:
        """An explicitly-chosen locale from the request — a ``?lang=``/``?locale=`` query param or a
        ``locale`` cookie (a language switcher). **Highest** precedence: an active choice beats the
        user's stored preference and ``Accept-Language``. Sanitized to a bare primary
        subtag (it feeds translation-file lookups, so an attacker-supplied value can't traverse paths
        or inject) -- anything that isn't a 2-8 letter code is ignored."""
        import re

        raw: Any = None
        if hasattr(request, "query"):
            raw = request.query("lang") or request.query("locale")
        if not raw and hasattr(request, "cookie"):
            raw = request.cookie("locale")
        if not raw:
            return None
        token = str(raw).split(",")[0].split("-")[0].split("_")[0].strip()
        return token if re.fullmatch(r"[A-Za-z]{2,8}", token) else None

    @staticmethod
    def user_preferred_locale() -> str | None:
        """The bound user's preferred locale (``locale``/``preferred_locale``), or ``None``.
        Public seam: ``AuthenticateMiddleware`` applies it after resolving the user (doc 21)."""
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


def _configured_max_request_size(default: int = 10 * 1024 * 1024) -> int:
    """``config('app.max_request_size')`` in bytes, falling back to ``default`` when unset/unbound
    — the one source ``ValidatePostSize`` and ``MethodOverride`` both enforce, so the two never
    disagree on the limit."""
    from arvel.kernel import app, has_application

    if has_application() and app().bound("config"):
        return int(app("config").get("app.max_request_size", default))
    return default


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
        return _configured_max_request_size(self.DEFAULT_MAX)

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
    """Share session-flashed data with this request's templates: the validation ``errors`` bag
    and the ``old`` callable for form repopulation. Web group, runs after ``StartSession`` (which sets ``request.session`` and
       ages the flash). No-op when no session or view is bound, so non-view apps are unaffected."""

    async def handle(self, request: Request, call_next: Callable[[Request], Awaitable[Any]]) -> Any:
        from arvel.kernel import app, has_application

        session = getattr(request, "session", None)
        if isinstance(session, dict) and has_application() and app().bound("view"):
            from arvel.http.flash import FlashBag

            bag = FlashBag(cast("dict[str, Any]", session))
            # request-scoped, NOT .share(): env.globals is process-wide and would leak this
            # request's flashed errors/old input into a concurrent request's render
            app("view").share_request(errors=bag.errors(), old=bag.old)
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


async def _send_413(send: Any) -> None:
    """A bare ASGI 413 response — ``MethodOverride`` runs ahead of Litestar's own middleware
    stack (where ``ValidatePostSize`` builds its ``Response``), so it must speak raw ASGI here."""
    body = b'{"message": "Payload too large."}'
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("latin-1")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


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

        # check Content-Length against ValidatePostSize's own limit BEFORE buffering — otherwise
        # an oversized body would be fully read into memory here, ahead of (and defeating) the
        # 413 gate that's supposed to refuse it first.
        length = headers.get(b"content-length")
        if length is not None:
            try:
                too_large = int(length) > _configured_max_request_size(ValidatePostSize.DEFAULT_MAX)
            except ValueError:
                too_large = False
            if too_large:
                await _send_413(send)
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
