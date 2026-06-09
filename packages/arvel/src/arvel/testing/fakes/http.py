"""HttpFake + the Http.fake/.assert_* machinery — records and stubs outbound HTTP."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from fnmatch import fnmatch
from types import TracebackType
from typing import TYPE_CHECKING, Any, cast

import httpx2 as httpx

from arvel.http.client import Response, reset_fake, set_fake

if TYPE_CHECKING:
    from collections.abc import Mapping
    from contextvars import Token

    from arvel.http.client import FakeTransport, OutboundRequest


@dataclass(frozen=True, slots=True)
class RecordedRequest:
    """One outbound request captured by the fake."""

    method: str
    url: str
    headers: dict[str, str]
    params: dict[str, Any]
    data: Any

    def has_header(self, name: str, value: str | None = None) -> bool:
        if name not in self.headers:
            return False
        return value is None or self.headers[name] == value


class FakeResponse:
    """A stubbed response spec; turned into a real ``httpx.Response`` per request."""

    def __init__(
        self,
        body: object = None,
        status: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self._body = body
        self._status = status
        self._headers = dict(headers) if headers else None

    def build(self, method: str, url: str) -> Response:
        request = httpx.Request(method, url)
        body = self._body
        if body is None:
            raw = httpx.Response(self._status, headers=self._headers, request=request)
        elif isinstance(body, (str, bytes)):
            raw = httpx.Response(self._status, content=body, headers=self._headers, request=request)
        else:
            # Anything else is JSON. httpx's json= is typed Any; pass it through.
            raw = httpx.Response(
                self._status,
                json=cast("Any", body),
                headers=self._headers,
                request=request,
            )
        return Response(raw)


_DEFAULT_STUB = FakeResponse(status=200)
_SCHEME_RE = re.compile(r"^https?://")


@dataclass
class HttpFake:
    """In-memory transport — records requests and returns stubbed responses.

    With no stubs every request gets an empty 200. With stubs, the first
    glob-matching pattern wins (URL matched with and without scheme); unmatched
    requests still get the empty 200 so a fake never leaks to the network.
    """

    stubs: dict[str, FakeResponse] = field(default_factory=dict[str, FakeResponse])
    recorded: list[RecordedRequest] = field(default_factory=list[RecordedRequest])

    def handle(self, request: OutboundRequest) -> Response:
        self.recorded.append(
            RecordedRequest(
                method=request.method,
                url=request.url,
                headers=dict(request.headers),
                params=dict(request.params) if request.params else {},
                data=request.data,
            )
        )
        return self._match(request.url).build(request.method, request.url)

    def _match(self, url: str) -> FakeResponse:
        stripped = _SCHEME_RE.sub("", url)
        for pattern, spec in self.stubs.items():
            if fnmatch(url, pattern) or fnmatch(stripped, pattern):
                return spec
        return _DEFAULT_STUB


class HttpFakeContext:
    """Context manager installing an ``HttpFake`` as the active transport."""

    def __init__(self, stubs: Mapping[str, FakeResponse] | None = None) -> None:
        self.fake = HttpFake(stubs=dict(stubs) if stubs else {})
        self._token: Token[FakeTransport | None] | None = None

    def __enter__(self) -> HttpFake:
        self._token = set_fake(self.fake)
        return self.fake

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._token is not None:
            reset_fake(self._token)
            self._token = None


__all__ = ["FakeResponse", "HttpFake", "HttpFakeContext", "RecordedRequest"]
