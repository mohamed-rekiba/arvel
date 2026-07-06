"""arvel.client — the ``Http`` client over **httpx** (core; DR-0002).

A fluent, async HTTP client: request builders
(``retry``/``timeout``/``as_form``/``as_multipart``/``attach``/auth helpers/…), a typed
``ClientResponse`` wrapper (``ok``/``json``/``throw``/…), ``pool`` for concurrent requests, and
``fake``/``assert_sent`` for testing without the network. Separate from the ``[http]`` web module.
httpx is core.
"""

from __future__ import annotations

import asyncio
import copy
import fnmatch
import json as _json
import weakref
from collections.abc import Callable, Mapping
from typing import Any, cast

import httpx

from arvel.telemetry import span

# --- exceptions -----------------------------------------------------------------


class RequestFailed(Exception):
    """Raised by ``ClientResponse.throw()`` (or an exhausted ``retry()``) when the response is
    ``failed()`` (4xx/5xx). Carries the ``response`` so callers can inspect status/body."""

    def __init__(self, response: ClientResponse) -> None:
        self.response = response
        super().__init__(f"HTTP request failed with status {response.status()}")


class StrayRequest(Exception):
    """Raised when ``Http.fake(...)`` has ``prevent_stray_requests()`` set and a request is made
    to a URL that matches none of the faked patterns."""


# --- dotted-key json access -------------------------------------------------------


def _dotted_get(data: Any, key: str, default: Any) -> Any:
    """dotted-key lookup into parsed JSON (``"user.name"``, ``"items.0.id"``)."""
    current: Any = data
    for part in key.split("."):
        if isinstance(current, Mapping) and part in current:
            mapping = cast("Mapping[str, Any]", current)
            current = mapping[part]
            continue
        if isinstance(current, list) and part.lstrip("-").isdigit():
            items = cast("list[Any]", current)
            index = int(part)
            if -len(items) <= index < len(items):
                current = items[index]
                continue
        return default
    return current


# --- response wrapper --------------------------------------------------------------


class ClientResponse:
    """Wraps an ``httpx.Response`` (composition; ``.raw`` is the escape hatch to the full httpx
    surface). All ``Http``/``PendingRequest`` verb methods return this."""

    def __init__(self, raw: httpx.Response) -> None:
        self.raw = raw

    def status(self) -> int:
        return self.raw.status_code

    def body(self) -> str:
        return self.raw.text

    def content(self) -> bytes:
        """The raw response body as **bytes** — use this for binary payloads (images, files, PDFs);
        :meth:`body` is the text-decoded ``str`` and is lossy for non-text content."""
        return self.raw.content

    def json(self, key: str | None = None, default: Any = None) -> Any:
        """The parsed JSON body, or ``default`` if the body isn't valid JSON. With ``key``, a
        dotted-path lookup into the parsed value (``response.json("user.name")``)."""
        try:
            data = self.raw.json()
        except ValueError:
            return default
        if key is None:
            return data
        return _dotted_get(data, key, default)

    def header(self, name: str) -> str | None:
        value = self.raw.headers.get(name)
        return None if value is None else str(value)

    def headers(self) -> httpx.Headers:
        return self.raw.headers

    def ok(self) -> bool:
        return self.raw.status_code == 200  # exactly 200, distinct from successful() (any 2xx)

    def successful(self) -> bool:
        return 200 <= self.raw.status_code < 300

    def redirect(self) -> bool:
        return 300 <= self.raw.status_code < 400

    def client_error(self) -> bool:
        return 400 <= self.raw.status_code < 500

    def server_error(self) -> bool:
        return self.raw.status_code >= 500

    def failed(self) -> bool:
        return self.client_error() or self.server_error()

    def throw(self) -> ClientResponse:
        """Raise ``RequestFailed`` when ``failed()``; otherwise a no-op that returns ``self``
        (chainable: ``(await Http.get(url)).throw().json()``)."""
        if self.failed():
            raise RequestFailed(self)
        return self


# --- retry policy -------------------------------------------------------------------

_RETRY_EXCEPTIONS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.TimeoutException)


def _default_should_retry(outcome: Exception | ClientResponse) -> bool:
    """Default ``retry()`` policy: connection/timeout errors, or a 5xx response."""
    if isinstance(outcome, Exception):
        return isinstance(outcome, _RETRY_EXCEPTIONS)
    return outcome.server_error()


# --- request builder ----------------------------------------------------------------


class PendingRequest:
    """A configurable, sendable HTTP request. Builder methods (``with_headers``, ``retry``, …)
    return a clone (immutable-ish fluent chain — safe to reuse a builder across several
    independently-configured calls, e.g. inside ``Http.pool``); ``get``/``post``/… send ``self``."""

    def __init__(
        self, transport: Any = None, *, shared_client: httpx.AsyncClient | None = None
    ) -> None:
        self._headers: dict[str, str] = {}
        self._base_url: str = ""
        self._timeout: float = 30.0
        self._connect_timeout: float | None = None
        self._transport = transport
        self._shared_client = shared_client
        self._retry_times: int = 0
        self._retry_sleep_ms: int = 0
        self._retry_when: Callable[[Exception | ClientResponse], bool] | None = None
        self._send_mode: str | None = None  # None | "form" | "multipart"
        self._files: list[tuple[str, Any]] = []
        self._auth: httpx.Auth | None = None
        self._raw_body: bytes | str | None = None

    def _clone(self) -> PendingRequest:
        clone = copy.copy(self)
        clone._headers = dict(self._headers)
        clone._files = list(self._files)
        return clone

    # -- builders -------------------------------------------------------------

    def with_headers(self, headers: dict[str, str]) -> PendingRequest:
        clone = self._clone()
        clone._headers.update(headers)
        return clone

    def with_token(self, token: str, scheme: str = "Bearer") -> PendingRequest:
        return self.with_headers({"Authorization": f"{scheme} {token}"})

    def with_basic_auth(self, username: str, password: str) -> PendingRequest:
        clone = self._clone()
        clone._auth = httpx.BasicAuth(username, password)
        return clone

    def with_digest_auth(self, username: str, password: str) -> PendingRequest:
        clone = self._clone()
        clone._auth = httpx.DigestAuth(username, password)
        return clone

    def with_body(self, content: bytes | str, content_type: str | None = None) -> PendingRequest:
        """Set a raw request body (bypassing ``json``/``data``/``files``). Sets ``Content-Type``
        when given."""
        clone = self._clone()
        clone._raw_body = content
        if content_type:
            clone._headers["Content-Type"] = content_type
        return clone

    def base_url(self, url: str) -> PendingRequest:
        clone = self._clone()
        clone._base_url = url
        return clone

    def timeout(self, seconds: float) -> PendingRequest:
        clone = self._clone()
        clone._timeout = seconds
        return clone

    def connect_timeout(self, seconds: float) -> PendingRequest:
        clone = self._clone()
        clone._connect_timeout = seconds
        return clone

    def retry(
        self,
        times: int,
        sleep_ms: int = 0,
        *,
        when: Callable[[Exception | ClientResponse], bool] | None = None,
    ) -> PendingRequest:
        """Attempt the request up to ``times`` times total, sleeping ``sleep_ms`` between
        attempts. Retries connect errors and 5xx responses by default; ``when(exc_or_response)``
        overrides that policy. Raises when every attempt is retry-worthy (the last exception, or
        ``RequestFailed`` for a persistent bad-status response).

        Note: a custom ``when`` that stays truthy on a *successful* response (e.g. content-based
        polling) still raises ``RequestFailed`` once ``times`` is exhausted, even though the final
        response is 2xx — exhaustion-with-``when`` always raises. Inspect the returned response
        instead if you want to poll without an exception."""
        clone = self._clone()
        clone._retry_times = times
        clone._retry_sleep_ms = sleep_ms
        clone._retry_when = when
        return clone

    def as_form(self) -> PendingRequest:
        """Send the body ``application/x-www-form-urlencoded`` (use ``data=`` on the verb call)."""
        clone = self._clone()
        clone._send_mode = "form"
        clone._headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
        return clone

    def as_multipart(self) -> PendingRequest:
        """Send the body ``multipart/form-data`` (pair with ``attach()`` for file parts)."""
        clone = self._clone()
        clone._send_mode = "multipart"
        return clone

    def attach(
        self,
        name: str,
        content: bytes,
        filename: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> PendingRequest:
        """Queue a multipart file part (implies ``as_multipart()``)."""
        clone = self._clone()
        content_type = (headers or {}).get("Content-Type")
        clone._files.append((name, (filename, content, content_type, dict(headers or {}))))
        clone._send_mode = "multipart"
        return clone

    def accept(self, content_type: str) -> PendingRequest:
        return self.with_headers({"Accept": content_type})

    def accept_json(self) -> PendingRequest:
        return self.accept("application/json")

    # -- sending ----------------------------------------------------------------

    def _effective_timeout(self) -> httpx.Timeout | float:
        if self._connect_timeout is None:
            return self._timeout
        return httpx.Timeout(self._timeout, connect=self._connect_timeout)

    def _resolve_url(self, url: str) -> str:
        if (
            self._shared_client is not None
            and self._base_url
            and not url.startswith(("http://", "https://"))
        ):
            return f"{self._base_url.rstrip('/')}/{url.lstrip('/')}"
        return url

    def _prepare_body(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        if self._send_mode == "form" and "json" in kwargs and "data" not in kwargs:
            kwargs["data"] = kwargs.pop("json")
        if self._files:
            existing: Any = kwargs.get("files")
            merged: list[tuple[str, Any]] = []
            if isinstance(existing, Mapping):
                merged.extend(cast("Mapping[str, Any]", existing).items())
            elif existing:
                merged.extend(cast("list[tuple[str, Any]]", existing))
            merged.extend(self._files)
            kwargs["files"] = merged
        if self._raw_body is not None and not any(
            k in kwargs for k in ("content", "data", "json", "files")
        ):
            kwargs["content"] = self._raw_body
        return kwargs

    async def _send_once(self, method: str, url: str, kwargs: dict[str, Any]) -> httpx.Response:
        send_kwargs = dict(kwargs)
        if self._auth is not None:
            send_kwargs.setdefault("auth", self._auth)
        if self._shared_client is not None:
            send_kwargs.setdefault("timeout", self._effective_timeout())
            return await self._shared_client.request(method, self._resolve_url(url), **send_kwargs)
        async with httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._effective_timeout(),
            transport=self._transport,
        ) as client:
            return await client.request(method, url, **send_kwargs)

    async def _send_with_retry(
        self, method: str, url: str, kwargs: dict[str, Any]
    ) -> httpx.Response:
        times = max(1, self._retry_times or 1)
        should_retry = self._retry_when or _default_should_retry
        last_exc: Exception | None = None
        last_response: httpx.Response | None = None
        for attempt in range(1, times + 1):
            try:
                last_response = await self._send_once(method, url, kwargs)
                last_exc = None
                retry_worthy = should_retry(ClientResponse(last_response))
            except (
                Exception
            ) as exc:  # re-raised below when not retry-worthy (or the loop keeps going)
                last_exc = exc
                last_response = None
                retry_worthy = should_retry(exc)
            if attempt == times or not retry_worthy:
                break
            if self._retry_sleep_ms:
                await asyncio.sleep(self._retry_sleep_ms / 1000)
        if last_exc is not None:
            raise last_exc
        if last_response is None:  # invariant: the loop always ends with an exception or a response
            raise RuntimeError("retry loop produced neither a response nor an exception")
        if self._retry_times > 0 and should_retry(ClientResponse(last_response)):
            raise RequestFailed(ClientResponse(last_response))
        return last_response

    async def request(self, method: str, url: str, **kwargs: Any) -> ClientResponse:
        kwargs = self._prepare_body(dict(kwargs))
        call_headers: dict[str, str] = kwargs.pop("headers", None) or {}
        headers = {**self._headers, **call_headers}
        with span(
            f"HTTP {method.upper()}",
            kind="client",
            attributes={"http.request.method": method.upper(), "url.full": str(url)},
        ) as sp:
            if sp is not None:
                from opentelemetry.propagate import inject

                inject(headers)  # W3C traceparent → the callee continues this trace (distributed)
            kwargs["headers"] = headers
            raw = await self._send_with_retry(method, url, kwargs)
            if sp is not None:
                sp.set_attribute("http.response.status_code", raw.status_code)
                if raw.status_code >= 400:
                    from opentelemetry.trace import Status, StatusCode

                    sp.set_status(Status(StatusCode.ERROR))
            return ClientResponse(raw)

    async def get(self, url: str, **kwargs: Any) -> ClientResponse:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> ClientResponse:
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> ClientResponse:
        return await self.request("PUT", url, **kwargs)

    async def patch(self, url: str, **kwargs: Any) -> ClientResponse:
        return await self.request("PATCH", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> ClientResponse:
        return await self.request("DELETE", url, **kwargs)


class PoolBuilder(PendingRequest):
    """Passed to the ``Http.pool(...)`` callback. Verb calls (``pool.get(url)``, …) return an
    unawaited coroutine — collect them in a list; ``pool`` gathers them concurrently on one
    shared connection."""


# --- fake response stub + recorded request ------------------------------------------


class FakeResponse:
    """A canned response, built via ``Http.response(...)``, for use with ``Http.fake({...})``."""

    def __init__(
        self, body: Any = "", status: int = 200, headers: dict[str, str] | None = None
    ) -> None:
        self.body = body
        self.status = status
        self.headers = headers or {}

    def to_httpx(self) -> httpx.Response:
        body: Any = self.body
        if isinstance(body, bytes):
            return httpx.Response(self.status, content=body, headers=self.headers)
        if isinstance(body, Mapping | list):
            return httpx.Response(self.status, json=cast("Any", body), headers=self.headers)
        return httpx.Response(self.status, text=str(body), headers=self.headers)


class RecordedRequest:
    """A request captured while ``Http.fake()`` is active — read via ``Http.recorded()`` /
    ``assert_sent``/``assert_not_sent`` predicates."""

    def __init__(self, raw: httpx.Request) -> None:
        self.raw = raw

    @property
    def method(self) -> str:
        return self.raw.method

    @property
    def url(self) -> str:
        return str(self.raw.url)

    @property
    def headers(self) -> httpx.Headers:
        return self.raw.headers

    @property
    def content(self) -> bytes:
        return self.raw.content

    def json(self, key: str | None = None, default: Any = None) -> Any:
        try:
            data = _json.loads(self.raw.content or b"{}")
        except ValueError:
            return default
        if key is None:
            return data
        return _dotted_get(data, key, default)


FakeHandler = Callable[[RecordedRequest], FakeResponse]


class _FakeState:
    """Per-``fake()`` state: the url-pattern → stub mapping, recorded requests, and the
    ``prevent_stray_requests`` flag."""

    def __init__(self, mapping: Mapping[str, FakeResponse | FakeHandler] | None) -> None:
        self.mapping = mapping
        self.prevent_stray = False
        self.recorded: list[RecordedRequest] = []

    def _match(self, url: str) -> FakeResponse | FakeHandler | None:
        if not self.mapping:
            return None
        for pattern, stub in self.mapping.items():
            if fnmatch.fnmatch(url, pattern):
                return stub
        return None

    async def handle(self, request: httpx.Request) -> httpx.Response:
        recorded = RecordedRequest(request)
        self.recorded.append(recorded)
        stub = self._match(str(request.url))
        if stub is None:
            if self.mapping is None:  # blanket `Http.fake()` — every request gets a default stub
                return FakeResponse().to_httpx()
            if self.prevent_stray:
                raise StrayRequest(
                    f"Http.fake: stray request to {request.url} (prevent_stray_requests is on)"
                )
            async with httpx.AsyncClient() as passthrough:  # not faked — let it hit the network
                return await passthrough.send(request)
        if callable(stub) and not isinstance(stub, FakeResponse):
            stub = stub(recorded)
        return stub.to_httpx()


class _Fake:
    """Context manager returned by ``Http.fake(...)``; restores the real transport on exit. Using
    it as a plain call (no ``with``) is also valid — call ``Http.restore()`` yourself."""

    def __init__(self, client: Client) -> None:
        self._client = client

    def __enter__(self) -> _Fake:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self._client.restore()


# --- the Http factory ----------------------------------------------------------------


class Client:
    """The ``Http`` factory (bound as ``http``, a container singleton). Each verb call starts a
    fresh request; ``fake()``/``restore()`` and the recorded requests are shared state on this
    instance, matching the singleton's lifetime."""

    def __init__(self, transport: Any = None) -> None:
        self._transport = transport
        self._fake_state: _FakeState | None = None
        # one keep-alive client per event loop, so sequential Http.get/post reuse connections
        # instead of building and tearing one down per call. Weak-keyed on the loop object:
        # an AsyncClient is bound to the loop it runs on, and a dead loop's entry must die
        # with it — an id()-keyed dict could hand a recycled loop address a client bound to
        # a collected loop. Closed on app shutdown (see the provider).
        self._shared: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, httpx.AsyncClient] = (
            weakref.WeakKeyDictionary()
        )

    def _current_transport(self) -> Any:
        if self._fake_state is not None:
            return httpx.MockTransport(self._fake_state.handle)
        return self._transport

    def _shared_client(self) -> httpx.AsyncClient | None:
        if self._fake_state is not None:
            return None  # faking swaps the transport per call — no shared client
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return None  # no running loop → fall back to a per-call client
        try:
            client = self._shared.get(loop)
            if client is None or client.is_closed:
                client = httpx.AsyncClient(transport=self._transport)
                self._shared[loop] = client
        except TypeError:
            # a host-installed loop type without weakref support can't be a key;
            # per-call behavior (same as the no-loop branch) beats failing the request
            return None
        return client

    async def aclose(self) -> None:
        """Close the pooled keep-alive clients — wired to app shutdown by the provider."""
        for client in list(self._shared.values()):  # snapshot: GC may prune during iteration
            if not client.is_closed:
                await client.aclose()
        self._shared.clear()

    def _pending(self) -> PendingRequest:
        return PendingRequest(
            transport=self._current_transport(), shared_client=self._shared_client()
        )

    # -- builder passthroughs (mirror PendingRequest) --------------------------

    def with_headers(self, headers: dict[str, str]) -> PendingRequest:
        return self._pending().with_headers(headers)

    def with_token(self, token: str, scheme: str = "Bearer") -> PendingRequest:
        return self._pending().with_token(token, scheme)

    def with_basic_auth(self, username: str, password: str) -> PendingRequest:
        return self._pending().with_basic_auth(username, password)

    def with_digest_auth(self, username: str, password: str) -> PendingRequest:
        return self._pending().with_digest_auth(username, password)

    def with_body(self, content: bytes | str, content_type: str | None = None) -> PendingRequest:
        return self._pending().with_body(content, content_type)

    def base_url(self, url: str) -> PendingRequest:
        return self._pending().base_url(url)

    def timeout(self, seconds: float) -> PendingRequest:
        return self._pending().timeout(seconds)

    def connect_timeout(self, seconds: float) -> PendingRequest:
        return self._pending().connect_timeout(seconds)

    def retry(
        self,
        times: int,
        sleep_ms: int = 0,
        *,
        when: Callable[[Exception | ClientResponse], bool] | None = None,
    ) -> PendingRequest:
        return self._pending().retry(times, sleep_ms, when=when)

    def as_form(self) -> PendingRequest:
        return self._pending().as_form()

    def as_multipart(self) -> PendingRequest:
        return self._pending().as_multipart()

    def attach(
        self,
        name: str,
        content: bytes,
        filename: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> PendingRequest:
        return self._pending().attach(name, content, filename, headers)

    def accept(self, content_type: str) -> PendingRequest:
        return self._pending().accept(content_type)

    def accept_json(self) -> PendingRequest:
        return self._pending().accept_json()

    # -- verbs ------------------------------------------------------------------

    async def get(self, url: str, **kwargs: Any) -> ClientResponse:
        return await self._pending().get(url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> ClientResponse:
        return await self._pending().post(url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> ClientResponse:
        return await self._pending().put(url, **kwargs)

    async def patch(self, url: str, **kwargs: Any) -> ClientResponse:
        return await self._pending().patch(url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> ClientResponse:
        return await self._pending().delete(url, **kwargs)

    # -- pool ---------------------------------------------------------------------

    async def pool(self, callback: Callable[[PoolBuilder], list[Any]]) -> list[Any]:
        """Run the ``PendingRequest`` calls the callback queues concurrently on one shared
        connection; returns ordered results — a failed slot holds the exception, it isn't
        raised."""
        async with httpx.AsyncClient(transport=self._current_transport()) as shared:
            builder = PoolBuilder(shared_client=shared)
            awaitables = callback(builder)
            return await asyncio.gather(*awaitables, return_exceptions=True)

    # -- fake + assertions ----------------------------------------------------------

    def fake(self, mapping: Mapping[str, FakeResponse | FakeHandler] | None = None) -> _Fake:
        """Swap in a ``MockTransport`` (context manager + plain call; ``restore()`` undoes it).
        ``mapping`` is ``{url_pattern: Http.response(...) | callable}`` with ``fnmatch`` wildcards
        against the full URL; ``None`` fakes every request with a generic 200. Unmatched URLs pass
        through to the real network unless ``prevent_stray_requests()`` is set."""
        self._fake_state = _FakeState(mapping)
        return _Fake(self)

    def restore(self) -> None:
        """Undo ``fake()`` — real requests hit the network again."""
        self._fake_state = None

    def response(
        self, body: Any = "", status: int = 200, headers: dict[str, str] | None = None
    ) -> FakeResponse:
        """Build a canned response for ``Http.fake({...})``."""
        return FakeResponse(body=body, status=status, headers=headers)

    def prevent_stray_requests(self, enabled: bool = True) -> None:
        """Requires an active ``fake()``: raise ``StrayRequest`` for any request that matches no
        faked pattern (instead of passing it through to the network).

        Note: a blanket ``fake()`` (called with no mapping) stubs *every* URL with a default
        response, so no request is ever "stray" and this check never fires — pass an explicit
        mapping if you want unmatched URLs to raise."""
        if self._fake_state is None:
            raise RuntimeError("prevent_stray_requests() requires an active Http.fake()")
        self._fake_state.prevent_stray = enabled

    def recorded(
        self, predicate: Callable[[RecordedRequest], bool] | None = None
    ) -> list[RecordedRequest]:
        """Requests captured since the last ``fake()`` call, optionally filtered by ``predicate``.
        Empty when no fake is active."""
        if self._fake_state is None:
            return []
        records = self._fake_state.recorded
        return list(records) if predicate is None else [r for r in records if predicate(r)]

    def assert_sent(self, predicate: Callable[[RecordedRequest], bool]) -> None:
        if not any(predicate(r) for r in self.recorded()):
            raise AssertionError(
                "Expected a request matching the given predicate, but none was recorded."
            )

    def assert_not_sent(self, predicate: Callable[[RecordedRequest], bool]) -> None:
        if any(predicate(r) for r in self.recorded()):
            raise AssertionError(
                "Expected no request matching the given predicate, but one was recorded."
            )

    def assert_sent_count(self, n: int) -> None:
        count = len(self.recorded())
        if count != n:
            raise AssertionError(f"Expected {n} request(s) to be sent, but {count} were recorded.")


__all__ = [
    "Client",
    "ClientResponse",
    "FakeResponse",
    "PendingRequest",
    "PoolBuilder",
    "RecordedRequest",
    "RequestFailed",
    "StrayRequest",
]
