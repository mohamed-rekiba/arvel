"""arvel.http.Request — a thin wrapper over a Litestar request + request scope.

Litestar is **not** imported here (it is lazy-imported in the kernel's serve path);
this wraps whatever request object Litestar passes in, kept as ``Any``. Per-request
state lives in ``ContextVar``s (no per-request rebinding). Grounded in doc 04.
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

    from arvel.support import Collection

current_request: contextvars.ContextVar[Request] = contextvars.ContextVar("arvel_request")
# re-exported from the core `support` leaf so http reads the principal without an http->auth edge
from arvel.support import current_user as current_user  # noqa: E402  (explicit re-export)

#: distinguishes "key absent" from "value is present and None" — a plain ``None`` default can't
#: (has/missing/filled all need that distinction over input()).
_MISSING: Any = object()


@dataclass(frozen=True)
class RouteMatch:
    """The matched route for the active request (H4): its name and resolved params (post-binding
    — a model-bound param carries the resolved model, not the raw path segment). Stashed on the
    ``Request`` by the kernel's dispatch; read via ``url().current_route()``/
    ``Router.current_route()``, never constructed directly."""

    name: str | None
    params: dict[str, Any] = field(default_factory=dict[str, Any])


def current_route_match() -> RouteMatch | None:
    """The active request's matched route, or ``None`` outside a request / before dispatch
    reaches binding resolution (there's no "current route" yet)."""
    request = current_request.get(None)
    if request is None:
        return None
    return getattr(request, "_route_match", None)


def route_matches_name(match: RouteMatch | None, pattern: str) -> bool:
    """Whether ``match`` is named and its name fnmatch-globs ``pattern`` — ``False`` for no match
    or an unnamed route."""
    import fnmatch

    return match is not None and match.name is not None and fnmatch.fnmatch(match.name, pattern)


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
    #: (encrypt_fn, decrypt_fn, except_names) stashed by ``EncryptCookies`` — absent when that
    #: middleware isn't wired in (or no encrypter is bound), in which case cookies stay plaintext.
    _cookie_codec: tuple[Callable[[str], str], Callable[[str], str], tuple[str, ...]]
    #: memoized normalized ``json()`` result — set on first call, absent before then.
    _json_cache: Any
    #: lazily created by :meth:`merge`/:meth:`merge_if_missing` — absent until first written.
    _input_overlay: dict[str, Any]
    #: the matched route (H4), set by the kernel once dispatch resolves bindings — absent before
    #: then / on a request the router never finished matching.
    _route_match: RouteMatch

    def __init__(self, litestar_request: Any) -> None:
        self._r = litestar_request
        # populated by TrimStrings/ConvertEmptyStringsToNull (H8) — each appends its transform in
        # pipeline order; json()/all() apply them so every input reader sees normalized data.
        self._input_transforms: list[Callable[[Any], Any]] = []

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
        """The cookie's value — decrypted when ``EncryptCookies`` is active and ``name`` isn't
        excepted (H7). A tampered/plaintext-leftover value fails decryption closed: treated as
        absent (``default``), never a 500."""
        cookies = getattr(self._r, "cookies", None)
        raw = cast("str | None", cookies.get(name) if cookies is not None else None)
        if raw is None:
            return default
        codec = getattr(self, "_cookie_codec", None)
        if codec is None or name in codec[2]:
            return raw
        from arvel.security import DecryptionFailed

        try:
            return cast("str", codec[1](raw))
        except DecryptionFailed:
            return default

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
        safe and lets schema validation report the missing fields cleanly.)

        Run through this request's ``_input_transforms`` (H8 — TrimStrings/ConvertEmptyStringsToNull,
        when wired into the global middleware) and cached: every caller (``input``/``all``/``validate``)
        sees the same normalized dict, computed once."""
        cached: Any = getattr(self, "_json_cache", _MISSING)
        if cached is not _MISSING:
            return cached
        try:
            data: Any = await self._r.json()
        except Exception as exc:
            # A syntactically-invalid JSON body is a client fault → the framework's 422, never a 500.
            # The transport wraps a msgspec decode error in its own SerializationException; match both
            # by runtime import (this only runs while serving, so the web engine is already loaded).
            import msgspec
            from litestar.exceptions import SerializationException

            if isinstance(exc, (SerializationException, msgspec.DecodeError, ValueError)):
                from arvel.validation import ValidationException

                raise ValidationException(
                    {"_body": ["The request body is not valid JSON."]}
                ) from exc
            raise
        if data is None:
            data = {}
        for transform in self._input_transforms:
            data = transform(data)
        self._json_cache = data
        return data

    async def validate(self, schema: Any) -> Any:
        """Validate the JSON body into ``schema`` (a FormRequest/Struct).

        Raises ``ValidationException`` (→ 422) on bad input, or ``AuthorizationException`` (→ 403)
        if the FormRequest's ``authorize()`` returns False — the same type
        ``FormRequest.authorized`` raises for the identical outcome (DR-0040).

        Validates the (normalized) **body** only: ``merge()`` overlay values appear in
        ``input()``/``all()`` but are deliberately invisible here — validation judges what
        the client actually sent.
        """
        from arvel.localization import trans
        from arvel.validation import (
            AuthorizationException,
            FormRequest,
            ValidationException,
            validate,
        )

        data = await self.json()
        raw_schema: Any = schema  # an un-narrowed Any handle for the generic validate path
        try:
            if isinstance(schema, type) and issubclass(schema, FormRequest):
                # the full lifecycle: structural (422) → authorize (403) → semantic rules (422) →
                # passed_validation. authorize runs before the semantic rules (AR-004/DR-0072) so a
                # denied caller gets a clean 403, not a 422 leaking the endpoint's rule contract.
                return cast("Any", schema.authorized(data))
            dto = validate(data, raw_schema)
        except ValidationException:
            self._flash_old_input(data)  # repopulate the redirected-back form via old()
            raise
        # a plain Schema has no rules() layer to order against — keep the post-structural authorize
        authorize = getattr(dto, "authorize", None)
        if callable(authorize) and not authorize():
            raise AuthorizationException(trans("http.unauthorized"))
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

    def _overlay(self) -> dict[str, Any]:
        """The ``merge``/``merge_if_missing`` overlay dict — created on first write, not in
        ``__init__`` (most requests never touch it)."""
        overlay: dict[str, Any] | None = getattr(self, "_input_overlay", None)
        if overlay is None:
            overlay = {}
            self._input_overlay = overlay
        return overlay

    def merge(self, mapping: Mapping[str, Any]) -> Request:
        """Overlay ``mapping`` onto every later ``input()``/``all()`` read, overwriting any
        existing key (query string or JSON body) with the same name."""
        self._overlay().update(mapping)
        return self

    async def merge_if_missing(self, mapping: Mapping[str, Any]) -> Request:
        """Like :meth:`merge`, but only for a key not already present anywhere in the input
        (query string, JSON body, or a prior merge) — an already-provided value always wins."""
        data = await self.all()
        overlay = self._overlay()
        for key, value in mapping.items():
            if key not in data:
                overlay[key] = value
        return self

    async def all(self) -> dict[str, Any]:
        """The full merged input: query params, overlaid by the JSON body (its keys win),
        overlaid by anything ``merge``d onto this request (the overlay always wins). A
        non-JSON/absent body contributes nothing — its keys just don't appear."""
        merged: dict[str, Any] = dict(self._r.query_params)
        for transform in self._input_transforms:  # query values get the same H8 normalization
            merged = transform(merged)
        try:
            body = await self.json()  # already normalized (json() runs the transforms itself)
        except Exception:
            body = None
        if isinstance(body, dict):
            merged.update(cast("dict[str, Any]", body))
        merged.update(self._overlay())
        return merged

    async def input(self, key: str | None = None, default: Any = None) -> Any:
        """No ``key`` → the full merged input (:meth:`all`). A dotted key (``"a.b"``) resolves via
        ``data_get`` over the merged input, so it can reach into a nested JSON body. A plain key
        stays on the fast top-level path — overlay, then JSON body, then query string — without
        paying for a full merge on every lookup.

        A non-JSON body (form-encoded, etc.) raises when parsed as JSON — swallow that and fall
        through to the query string rather than surface a decode error to the caller."""
        if key is None:
            return await self.all()
        if "." in key:
            from arvel.support.helpers import data_get

            return data_get(await self.all(), key, default)
        overlay = getattr(self, "_input_overlay", None)
        if overlay and key in overlay:
            return overlay[key]
        try:
            body = await self.json()
        except Exception:
            body = None
        if isinstance(body, dict) and key in body:
            return cast("dict[str, Any]", body)[key]
        raw = self.query(key, _MISSING)
        if raw is _MISSING:
            return default
        # run through the same transforms all()'s query side gets, keyed so except_ (by name)
        # still applies — input(key) and all()[key] must never disagree on a query value.
        transformed: dict[str, Any] = {key: raw}
        for transform in self._input_transforms:
            transformed = transform(transformed)
        return transformed[key]

    async def only(self, keys: Iterable[str]) -> dict[str, Any]:
        """The merged input narrowed to ``keys`` — a key absent from the input is simply omitted
        (not an error, not a ``None`` entry)."""
        data = await self.all()
        return {k: data[k] for k in keys if k in data}

    async def except_(self, keys: Iterable[str]) -> dict[str, Any]:
        """The merged input with ``keys`` removed."""
        data = await self.all()
        excluded = set(keys)
        return {k: v for k, v in data.items() if k not in excluded}

    async def has(self, key_or_list: str | Iterable[str]) -> bool:
        """Whether every given key is *present* in the input — true even for an empty-string or
        ``None`` value; see :meth:`filled` for "present and non-empty"."""
        keys = [key_or_list] if isinstance(key_or_list, str) else list(key_or_list)
        for k in keys:
            if (await self.input(k, _MISSING)) is _MISSING:
                return False
        return True

    async def has_any(self, keys: Iterable[str]) -> bool:
        """Whether at least one of ``keys`` is present."""
        for k in keys:
            if (await self.input(k, _MISSING)) is not _MISSING:
                return True
        return False

    async def filled(self, key: str) -> bool:
        """Present *and* not empty (``None``/``""``/``[]``/``{}``)."""
        value = await self.input(key, _MISSING)
        if value is _MISSING or value is None:
            return False
        return value not in ("", [], {})

    async def missing(self, key: str) -> bool:
        """The inverse of :meth:`has` for a single key."""
        return not await self.has(key)

    async def string(self, key: str, default: str = "") -> str:
        """``input(key)`` as ``str`` — ``default`` (not ``str(None)``) when absent/``None``."""
        value = await self.input(key)
        return default if value is None else str(value)

    async def integer(self, key: str, default: int = 0) -> int:
        """``input(key)`` coerced to ``int`` — ``default`` when absent/``None``/non-coercible."""
        value = await self.input(key)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError, TypeError:  # non-coercible incl. list/dict bodies
            return default

    async def boolean(self, key: str, default: bool = False) -> bool:
        """``input(key)`` coerced to bool — ``"1"/"true"/"on"/"yes"`` (any case) are True."""
        value = await self.input(key)
        if value is None:
            return default
        return str(value).strip().lower() in ("1", "true", "on", "yes")

    async def date(self, key: str, default: Any = None) -> Any:
        """``input(key)`` parsed as a :class:`~arvel.dates.Date` — ``default`` when absent or
        unparseable."""
        value = await self.input(key)
        if value is None:
            return default
        from arvel.dates import Date, DateParseError

        try:
            return Date.parse(value)
        except DateParseError:
            return default

    async def enum[E: Enum](self, key: str, enum_cls: type[E]) -> E | None:
        """``input(key)`` resolved to an ``enum_cls`` member by *value* — ``None`` when absent or
        the value doesn't match any member (never raises)."""
        value = await self.input(key)
        if value is None:
            return None
        try:
            return enum_cls(value)
        except ValueError:
            return None

    async def collect(self, key: str | None = None) -> Collection[Any]:
        """The merged input wrapped as a :class:`~arvel.support.Collection` — the full input as
        ``(key, value)`` pairs when ``key`` is absent, else the key's value as a list (a scalar
        becomes a one-item list; an already-list value passes through; an absent key gives an
        empty Collection)."""
        from arvel.support import Collection

        if key is None:
            data = await self.all()
            return Collection(list(data.items()))
        value = await self.input(key)
        if value is None:
            return Collection()
        if isinstance(value, list):
            return Collection(cast("list[Any]", value))
        return Collection([value])

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
