"""Outbound HTTP client — the engine behind the ``Http`` facade.

A small fluent wrapper over ``httpx`` (async). The fake hook lives here as a
ContextVar so test doubles can intercept requests without the runtime depending
on the testing package.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, Self, runtime_checkable

import httpx2 as httpx

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True, slots=True)
class OutboundRequest:
    """An outbound request handed to a fake transport (or about to hit the wire)."""

    method: str
    url: str
    headers: Mapping[str, str]
    params: Mapping[str, Any] | None
    data: Any
    body_format: str


@runtime_checkable
class FakeTransport(Protocol):
    """Implemented by the test fake; intercepts a request and returns a Response."""

    def handle(self, request: OutboundRequest) -> Response: ...


_active_fake: ContextVar[FakeTransport | None] = ContextVar("arvel_http_fake", default=None)

_HTTP_OK = 200
_HTTP_REDIRECT = 300
_HTTP_CLIENT_ERROR = 400
_HTTP_SERVER_ERROR = 500
_HTTP_RANGE_END = 600


def active_fake() -> FakeTransport | None:
    return _active_fake.get()


def set_fake(fake: FakeTransport | None) -> Token[FakeTransport | None]:
    """Install *fake* as the active transport; returns a token for :func:`reset_fake`."""
    return _active_fake.set(fake)


def reset_fake(token: Token[FakeTransport | None]) -> None:
    _active_fake.reset(token)


class Response:
    """Thin, predicate-rich wrapper over an ``httpx.Response`` (Laravel-style)."""

    def __init__(self, raw: httpx.Response) -> None:
        self._raw = raw

    @property
    def raw(self) -> httpx.Response:
        return self._raw

    def status(self) -> int:
        return self._raw.status_code

    def ok(self) -> bool:
        return self._raw.status_code == _HTTP_OK

    def successful(self) -> bool:
        return _HTTP_OK <= self._raw.status_code < _HTTP_REDIRECT

    def redirect(self) -> bool:
        return _HTTP_REDIRECT <= self._raw.status_code < _HTTP_CLIENT_ERROR

    def failed(self) -> bool:
        return self._raw.status_code >= _HTTP_CLIENT_ERROR

    def client_error(self) -> bool:
        return _HTTP_CLIENT_ERROR <= self._raw.status_code < _HTTP_SERVER_ERROR

    def server_error(self) -> bool:
        return _HTTP_SERVER_ERROR <= self._raw.status_code < _HTTP_RANGE_END

    def json(self) -> Any:
        return self._raw.json()

    def body(self) -> str:
        return self._raw.text

    def header(self, name: str) -> str | None:
        value = self._raw.headers.get(name)
        return None if value is None else str(value)

    def headers(self) -> dict[str, str]:
        return dict(self._raw.headers)

    def raise_for_status(self) -> Self:
        self._raw.raise_for_status()
        return self


class PendingRequest:
    """Fluent builder for one outbound request. Each verb method sends it."""

    def __init__(self) -> None:
        self._headers: dict[str, str] = {}
        self._timeout: float | None = None
        self._base_url: str = ""
        self._auth: tuple[str, str] | None = None
        self._body_format: str = "json"

    def with_headers(self, headers: Mapping[str, str]) -> Self:
        self._headers.update(headers)
        return self

    def with_token(self, token: str, scheme: str = "Bearer") -> Self:
        self._headers["Authorization"] = f"{scheme} {token}"
        return self

    def with_basic_auth(self, username: str, password: str) -> Self:
        self._auth = (username, password)
        return self

    def accept(self, content_type: str) -> Self:
        self._headers["Accept"] = content_type
        return self

    def accept_json(self) -> Self:
        return self.accept("application/json")

    def as_json(self) -> Self:
        self._body_format = "json"
        return self

    def as_form(self) -> Self:
        self._body_format = "form"
        return self

    def timeout(self, seconds: float) -> Self:
        self._timeout = seconds
        return self

    def base_url(self, url: str) -> Self:
        self._base_url = url
        return self

    async def get(self, url: str, query: Mapping[str, Any] | None = None) -> Response:
        return await self.send("GET", url, query=query)

    async def head(self, url: str, query: Mapping[str, Any] | None = None) -> Response:
        return await self.send("HEAD", url, query=query)

    async def post(self, url: str, data: Any = None) -> Response:
        return await self.send("POST", url, data=data)

    async def put(self, url: str, data: Any = None) -> Response:
        return await self.send("PUT", url, data=data)

    async def patch(self, url: str, data: Any = None) -> Response:
        return await self.send("PATCH", url, data=data)

    async def delete(self, url: str, data: Any = None) -> Response:
        return await self.send("DELETE", url, data=data)

    def _resolve_url(self, url: str) -> str:
        if not self._base_url or url.startswith(("http://", "https://")):
            return url
        return f"{self._base_url.rstrip('/')}/{url.lstrip('/')}"

    async def send(
        self,
        method: str,
        url: str,
        *,
        query: Mapping[str, Any] | None = None,
        data: Any = None,
    ) -> Response:
        full_url = self._resolve_url(url)
        fake = _active_fake.get()
        if fake is not None:
            return fake.handle(
                OutboundRequest(
                    method=method,
                    url=full_url,
                    headers=self._headers,
                    params=query,
                    data=data,
                    body_format=self._body_format,
                )
            )
        json_body = data if data is not None and self._body_format == "json" else None
        form_body = data if data is not None and self._body_format == "form" else None
        auth = httpx.BasicAuth(*self._auth) if self._auth is not None else None
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            raw = await client.request(
                method,
                full_url,
                headers=self._headers or None,
                params=dict(query) if query else None,
                json=json_body,
                data=form_body,
                auth=auth,
            )
        return Response(raw)


__all__ = [
    "FakeTransport",
    "OutboundRequest",
    "PendingRequest",
    "Response",
    "active_fake",
    "reset_fake",
    "set_fake",
]
