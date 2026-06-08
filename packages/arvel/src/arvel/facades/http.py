"""Http facade — fluent outbound HTTP, with a test fake.

resp = await Http.with_token(tok).accept_json().get("https://api.example.com/me")
if resp.successful():
    data = resp.json()
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from arvel.http.client import PendingRequest, Response, active_fake

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from arvel.testing.fakes.http import FakeResponse, HttpFake, HttpFakeContext, RecordedRequest


class Http:
    """Classmethod entry point for outbound requests. Stateless — no binding needed."""

    # ── Request builders (each returns a fresh PendingRequest) ──────────────────

    @classmethod
    def with_headers(cls, headers: Mapping[str, str]) -> PendingRequest:
        return PendingRequest().with_headers(headers)

    @classmethod
    def with_token(cls, token: str, scheme: str = "Bearer") -> PendingRequest:
        return PendingRequest().with_token(token, scheme)

    @classmethod
    def with_basic_auth(cls, username: str, password: str) -> PendingRequest:
        return PendingRequest().with_basic_auth(username, password)

    @classmethod
    def accept(cls, content_type: str) -> PendingRequest:
        return PendingRequest().accept(content_type)

    @classmethod
    def accept_json(cls) -> PendingRequest:
        return PendingRequest().accept_json()

    @classmethod
    def as_form(cls) -> PendingRequest:
        return PendingRequest().as_form()

    @classmethod
    def timeout(cls, seconds: float) -> PendingRequest:
        return PendingRequest().timeout(seconds)

    @classmethod
    def base_url(cls, url: str) -> PendingRequest:
        return PendingRequest().base_url(url)

    # ── Verbs (shorthand for an unconfigured request) ───────────────────────────

    @classmethod
    async def get(cls, url: str, query: Mapping[str, Any] | None = None) -> Response:
        return await PendingRequest().get(url, query)

    @classmethod
    async def head(cls, url: str, query: Mapping[str, Any] | None = None) -> Response:
        return await PendingRequest().head(url, query)

    @classmethod
    async def post(cls, url: str, data: Any = None) -> Response:
        return await PendingRequest().post(url, data)

    @classmethod
    async def put(cls, url: str, data: Any = None) -> Response:
        return await PendingRequest().put(url, data)

    @classmethod
    async def patch(cls, url: str, data: Any = None) -> Response:
        return await PendingRequest().patch(url, data)

    @classmethod
    async def delete(cls, url: str, data: Any = None) -> Response:
        return await PendingRequest().delete(url, data)

    # ── Testing ─────────────────────────────────────────────────────────────────

    @classmethod
    def fake(cls, stubs: Mapping[str, FakeResponse] | None = None) -> HttpFakeContext:
        """Intercept outbound requests. Use as ``with Http.fake({...}) as fake:``."""
        from arvel.testing.fakes.http import HttpFakeContext

        return HttpFakeContext(stubs)

    @classmethod
    def response(
        cls,
        body: object = None,
        status: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> FakeResponse:
        """Build a stub response for :meth:`fake`."""
        from arvel.testing.fakes.http import FakeResponse

        return FakeResponse(body, status, headers)

    @classmethod
    def _active(cls, action: str) -> HttpFake:
        from arvel.testing.fakes.http import HttpFake

        fake = active_fake()
        if not isinstance(fake, HttpFake):
            raise TypeError(f"Http.{action} requires an active Http.fake() context")
        return fake

    @classmethod
    def recorded(cls) -> list[RecordedRequest]:
        return list(cls._active("recorded").recorded)

    @classmethod
    def assert_sent(cls, predicate: Callable[[RecordedRequest], bool]) -> None:
        fake = cls._active("assert_sent")
        if not any(predicate(req) for req in fake.recorded):
            raise AssertionError("No recorded request matched the predicate")

    @classmethod
    def assert_not_sent(cls, predicate: Callable[[RecordedRequest], bool]) -> None:
        fake = cls._active("assert_not_sent")
        if any(predicate(req) for req in fake.recorded):
            raise AssertionError("A recorded request matched the predicate")

    @classmethod
    def assert_sent_count(cls, count: int) -> None:
        fake = cls._active("assert_sent_count")
        actual = len(fake.recorded)
        if actual != count:
            raise AssertionError(f"Expected {count} sent request(s), got {actual}")

    @classmethod
    def assert_nothing_sent(cls) -> None:
        fake = cls._active("assert_nothing_sent")
        if fake.recorded:
            raise AssertionError(f"Expected no requests, got {len(fake.recorded)}")


__all__ = ["Http"]
