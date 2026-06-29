"""arvel.http.Request — a thin wrapper over a Litestar request + request scope.

Litestar is **not** imported here (it is lazy-imported in the kernel's serve path);
this wraps whatever request object Litestar passes in, kept as ``Any``. Per-request
state lives in ``ContextVar``s (no per-request rebinding). Grounded in doc 04.
"""

from __future__ import annotations

import contextvars
from typing import Any, cast

current_request: contextvars.ContextVar[Request] = contextvars.ContextVar("arvel_request")
# Re-exported from the core ``support`` leaf so http can read/baseline the principal without an
# illegal http→auth edge; ``auth`` re-exports the same object as its public ``current_user`` (DR-0026).
from arvel.support import current_user as current_user  # noqa: E402  (explicit re-export)


class Request:
    def __init__(self, litestar_request: Any) -> None:
        self._r = litestar_request

    @property
    def raw(self) -> Any:
        return self._r

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
        """Whether X-Forwarded-* headers may be trusted — Laravel ``TrustProxies``. Driven by
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

    #: input fields never flashed back (Laravel ``dontFlash``) — keep secrets out of the session.
    _DONT_FLASH = ("password", "password_confirmation")

    def _flash_old_input(self, data: Any) -> None:
        """Flash the submitted input (minus passwords) so ``old()`` can repopulate the form after a
        validation redirect-back. No-op off the web group (no ``session`` attribute) — see kernel S1."""
        session = getattr(self, "session", None)
        if isinstance(session, dict) and isinstance(data, dict):
            from arvel.http.flash import FlashBag

            payload = cast("dict[str, Any]", data)
            safe = {k: v for k, v in payload.items() if k not in self._DONT_FLASH}
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

    def is_(self, pattern: str) -> bool:
        from fnmatch import fnmatch

        return fnmatch(self.path().lstrip("/"), pattern)


class UploadedFile:
    """A thin wrapper over a framework upload (a Litestar ``UploadFile``) that adds Laravel-style
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


# Wire pagination's current-request resolver (http→pagination is a legal downward edge;
# pagination must not import http — DR-0026). Importing arvel.http.request is enough to make
# ``await Post.paginate()`` resolve the bound request for URL/page building.
import arvel.pagination as _pagination  # noqa: E402

_pagination.set_request_resolver(lambda: current_request.get(None))
