"""arvel.http.Request — a thin wrapper over a Litestar request + request scope.

Litestar is **not** imported here (it is lazy-imported in the kernel's serve path);
this wraps whatever request object Litestar passes in, kept as ``Any``. Per-request
state lives in ``ContextVar``s (no per-request rebinding). Grounded in doc 04.
"""

from __future__ import annotations

import contextvars
from typing import Any, cast

current_request: contextvars.ContextVar[Request] = contextvars.ContextVar("arvel_request")
# re-exported from the core `support` leaf so http reads the principal without an http->auth edge
from arvel.support import current_user as current_user  # noqa: E402  (explicit re-export)


class Request:
    #: web-group session state, attached by ``StartSession`` — absent until then (no default here;
    #: ``getattr(request, "session", None)`` is still how everything off the web group checks for it).
    session: dict[str, Any]
    #: the live session id — set by ``StartSession``; rotated by ``regenerate_session``.
    _session_id: str
    #: old session ids to forget on request teardown (``arvel.http.session`` contract).
    _session_drop: set[str]
    #: whether ``StartSession.terminate`` should issue a ``Set-Cookie``.
    _session_set_cookie: bool

    def __init__(self, litestar_request: Any) -> None:
        self._r = litestar_request

    @property
    def raw(self) -> Any:
        return self._r

    async def body(self) -> bytes:
        """The raw request body bytes, before any parsing — e.g. to verify an HMAC signature over the
        exact received payload. Use :meth:`json`/:meth:`form` for parsed access."""
        return cast("bytes", await self._r.body())

    def method(self) -> str:
        return str(self._r.method)

    def path(self) -> str:
        return str(self._r.url.path)

    def header(self, name: str, default: str | None = None) -> str | None:
        return cast("str | None", self._r.headers.get(name, default))

    def cookie(self, name: str, default: str | None = None) -> str | None:
        cookies = getattr(self._r, "cookies", None)
        return cast("str | None", cookies.get(name, default)) if cookies is not None else default

    def _peer(self) -> str | None:
        """The raw socket peer IP (no proxy headers)."""
        client = getattr(self._r, "client", None)
        return cast("str | None", getattr(client, "host", None)) if client is not None else None

    def _trusts_proxies(self) -> bool:
        """Whether X-Forwarded-* headers may be trusted — ``TrustProxies``. Driven by
        ``config('app.trusted_proxies')``: ``'*'`` trusts all; a list trusts only when the socket
        peer is in it; unset/empty trusts none (the secure default — forwarded headers are
        client-spoofable otherwise)."""
        from arvel.kernel import app, has_application

        proxies: Any = None
        if has_application() and app().bound("config"):
            proxies = app("config").get("app.trusted_proxies")
        if proxies == "*" or proxies == ["*"]:
            return True
        if isinstance(proxies, (list, tuple)):
            return self._peer() in proxies
        return False

    def ip(self) -> str | None:
        """The client IP: the first X-Forwarded-For hop **only when proxies are trusted**
        (see ``_trusts_proxies``); otherwise the socket peer."""
        if self._trusts_proxies():
            forwarded = self.header("x-forwarded-for")
            if forwarded:
                return forwarded.split(",")[0].strip()
        return self._peer()

    def scheme(self) -> str:
        """``'http'``/``'https'`` — honors X-Forwarded-Proto only when proxies are trusted."""
        if self._trusts_proxies():
            proto = self.header("x-forwarded-proto")
            if proto:
                return proto.split(",")[0].strip().lower()
        return str(getattr(self._r.url, "scheme", "http") or "http")

    def is_secure(self) -> bool:
        """Whether the (effective) request scheme is HTTPS."""
        return self.scheme() == "https"

    def host(self) -> str | None:
        """The request host (no port) — honors X-Forwarded-Host only when proxies are trusted."""
        if self._trusts_proxies():
            forwarded = self.header("x-forwarded-host")
            if forwarded:
                return forwarded.split(",")[0].strip().split(":")[0]
        header = self.header("host")
        if header:
            return header.split(":")[0]
        return cast("str | None", getattr(self._r.url, "hostname", None))

    def query(self, key: str, default: Any = None) -> Any:
        return self._r.query_params.get(key, default)

    def path_param(self, key: str, default: Any = None) -> Any:
        return self._r.path_params.get(key, default)

    async def json(self) -> Any:
        """The parsed JSON body, or ``{}`` for a request with **no body**. (Litestar returns ``None``
        on an empty body, which makes the common ``(await request.json()).get(...)`` — and ``validate``
        — crash with ``'NoneType' has no attribute 'get'``; defaulting to an empty mapping keeps those
        safe and lets schema validation report the missing fields cleanly.)"""
        data = await self._r.json()
        return {} if data is None else data

    async def validate(self, schema: Any) -> Any:
        """Validate the JSON body into ``schema`` (a FormRequest/Struct).

        Raises ``ValidationException`` (→ 422) on bad input, or 403 if the
        FormRequest's ``authorize()`` returns False.
        """
        from arvel.localization import trans
        from arvel.validation import ValidationException, validate

        data = await self.json()
        try:
            dto = validate(data, schema)
        except ValidationException:
            self._flash_old_input(data)  # repopulate the redirected-back form via old()
            raise
        authorize = getattr(dto, "authorize", None)
        if callable(authorize) and not authorize():
            raise ValidationException(trans("http.unauthorized"), status=403)
        return dto

    #: input fields never flashed back — keep secrets out of the session.
    _DONT_FLASH = ("password", "password_confirmation")

    def _flash_old_input(self, data: Any, *, except_: tuple[str, ...] = ()) -> None:
        """Flash the submitted input (minus passwords, plus any caller-given ``except_`` fields) so
        ``old()`` can repopulate the form after a validation redirect-back or a
        ``redirect().with_input(except_=...)``. No-op off the web group (no ``session`` attribute)
        — see kernel S1."""
        session = getattr(self, "session", None)
        # `data` is a plain dict from `.json()`, but Litestar's `.form()` returns a `FormMultiDict`
        # (Mapping-like, not a `dict` instance) — duck-type on `.items()` so a form submission
        # flashes too, not just JSON.
        if isinstance(session, dict) and hasattr(data, "items"):
            from arvel.http.flash import FlashBag

            payload = dict(cast("dict[str, Any]", data).items())
            excluded = set(self._DONT_FLASH) | set(except_)
            safe = {k: v for k, v in payload.items() if k not in excluded}
            FlashBag(cast("dict[str, Any]", session)).flash_input(safe)

    async def form(self) -> Any:
        """The parsed multipart/urlencoded form (fields + uploaded files)."""
        return await self._r.form()

    async def file(self, name: str, default: Any = None) -> Any:
        """An uploaded file by field name as an ``UploadedFile`` (with ``.store()``), or
        ``default`` when the field is absent."""
        form = await self._r.form()
        upload = form.get(name)
        return UploadedFile(upload) if upload is not None else default

    def user(self) -> Any:
        return current_user.get()

    def bearer_token(self) -> str | None:
        """The token from an ``Authorization: Bearer <token>`` header, or None."""
        header = self.header("authorization")
        if header and header.lower().startswith("bearer "):
            return header[7:].strip()
        return None

    async def input(self, key: str, default: Any = None) -> Any:
        """A single value by key, looking in the JSON body first, then the query string.

        A non-JSON body (form-encoded, etc.) raises when parsed as JSON — swallow that and fall
        through to the query string rather than surface a decode error to the caller."""
        try:
            body = await self.json()
        except Exception:
            body = None
        if isinstance(body, dict) and key in body:
            return cast("dict[str, Any]", body)[key]
        return self.query(key, default)

    async def boolean(self, key: str, default: bool = False) -> bool:
        """``input(key)`` coerced to bool — ``"1"/"true"/"on"/"yes"`` (any case) are True."""
        value = await self.input(key)
        if value is None:
            return default
        return str(value).strip().lower() in ("1", "true", "on", "yes")

    def is_(self, pattern: str) -> bool:
        from fnmatch import fnmatch

        return fnmatch(self.path().lstrip("/"), pattern)


class UploadedFile:
    """A thin wrapper over a framework upload (a Litestar ``UploadFile``) that adds -style
    persistence: ``store()`` writes it to a configured disk via the filesystem manager and
    returns the stored path. Read/metadata accessors delegate to the underlying upload."""

    def __init__(self, upload: Any) -> None:
        self._upload = upload

    @property
    def client_name(self) -> str | None:
        """The original filename supplied by the client."""
        return getattr(self._upload, "filename", None)

    # ``.filename`` kept as an alias so existing handlers keep working.
    @property
    def filename(self) -> str | None:
        return getattr(self._upload, "filename", None)

    @property
    def content_type(self) -> str | None:
        return getattr(self._upload, "content_type", None)

    @property
    def extension(self) -> str:
        name = self.client_name or ""
        return name.rsplit(".", 1)[-1] if "." in name else ""

    async def read(self) -> bytes:
        return cast("bytes", await self._upload.read())

    async def store(self, directory: str = "", *, disk: str | None = None) -> str:
        """Persist under a hashed random filename in ``directory`` on ``disk`` (default disk);
        returns the stored path."""
        from arvel.support import Str

        ext = self.extension
        name = f"{Str.random(40)}.{ext}" if ext else Str.random(40)
        return await self.store_as(directory, name, disk=disk)

    async def store_as(self, directory: str, name: str, *, disk: str | None = None) -> str:
        """Persist under an explicit ``name`` in ``directory`` on ``disk``; returns the path."""
        from arvel.kernel import app

        path = f"{directory.rstrip('/')}/{name}" if directory else name
        await app("filesystem").disk(disk).put(path, await self._upload.read())
        return path


# importing this module wires pagination's current-request resolver, so `await Post.paginate()`
# can resolve the bound request for URL/page building
import arvel.pagination as _pagination  # noqa: E402

_pagination.set_request_resolver(lambda: current_request.get(None))
