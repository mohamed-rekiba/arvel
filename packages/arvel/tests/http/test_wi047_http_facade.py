"""Http facade — fluent client, response predicates, and the fake/assert API."""

from __future__ import annotations

import httpx2 as httpx
import pytest
from arvel.facades.http import Http
from arvel.http.client import Response


def _resp(status: int) -> Response:
    return Response(httpx.Response(status, request=httpx.Request("GET", "http://x")))


class TestResponsePredicates:
    def test_status_and_ok(self) -> None:
        assert _resp(200).ok() is True
        assert _resp(201).ok() is False
        assert _resp(200).status() == 200

    def test_ranges(self) -> None:
        assert _resp(204).successful() is True
        assert _resp(302).redirect() is True
        assert _resp(404).client_error() is True
        assert _resp(404).failed() is True
        assert _resp(500).server_error() is True
        assert _resp(500).failed() is True
        assert _resp(200).failed() is False

    def test_body_and_headers(self) -> None:
        raw = httpx.Response(
            200, content=b"hello", headers={"X-K": "v"}, request=httpx.Request("GET", "http://x")
        )
        resp = Response(raw)
        assert resp.body() == "hello"
        assert resp.header("x-k") == "v"
        assert resp.headers()["x-k"] == "v"

    def test_raise_for_status(self) -> None:
        with pytest.raises(httpx.HTTPStatusError):
            _resp(500).raise_for_status()


class TestUrlResolution:
    async def test_base_url_joins_relative(self) -> None:
        with Http.fake() as fake:
            await Http.base_url("https://api.example.com/v1").get("users")
        assert fake.recorded[0].url == "https://api.example.com/v1/users"

    async def test_absolute_url_ignores_base(self) -> None:
        with Http.fake() as fake:
            await Http.base_url("https://api.example.com").get("https://other.test/x")
        assert fake.recorded[0].url == "https://other.test/x"


class TestFakeBasics:
    async def test_no_stub_returns_empty_200(self) -> None:
        with Http.fake():
            resp = await Http.get("https://example.test/anything")
        assert resp.status() == 200
        assert resp.body() == ""

    async def test_json_stub(self) -> None:
        with Http.fake({"*": Http.response({"id": 1}, 200)}):
            resp = await Http.get("https://api.test/me")
        assert resp.successful()
        assert resp.json() == {"id": 1}

    async def test_pattern_match_and_default_fallback(self) -> None:
        stubs = {"api.example.com/*": Http.response({"matched": True}, 201)}
        with Http.fake(stubs):
            hit = await Http.get("https://api.example.com/users")
            miss = await Http.get("https://other.test/x")
        assert hit.status() == 201
        assert hit.json() == {"matched": True}
        assert miss.status() == 200  # unmatched -> default, never hits network

    async def test_status_stub(self) -> None:
        with Http.fake({"*": Http.response("nope", 404)}):
            resp = await Http.post("https://x.test/y", {"a": 1})
        assert resp.status() == 404
        assert resp.failed()


class TestRequestBuilders:
    """Each builder returns a fresh PendingRequest that still issues the request."""

    async def test_with_headers(self) -> None:
        with Http.fake() as fake:
            await Http.with_headers({"X-A": "1"}).get("https://x.test/h")
        assert fake.recorded[0].has_header("X-A", "1")

    async def test_with_basic_auth(self) -> None:
        # Basic auth is applied via httpx's auth hook at send time, not the header
        # dict the fake records — so just assert the builder issued the request.
        with Http.fake() as fake:
            await Http.with_basic_auth("ada", "secret").get("https://x.test/b")
        assert fake.recorded[0].url == "https://x.test/b"

    async def test_accept(self) -> None:
        with Http.fake() as fake:
            await Http.accept("application/xml").get("https://x.test/a")
        assert fake.recorded[0].has_header("Accept", "application/xml")

    async def test_accept_json(self) -> None:
        with Http.fake() as fake:
            await Http.accept_json().get("https://x.test/j")
        assert fake.recorded[0].has_header("Accept", "application/json")

    async def test_as_form_and_timeout(self) -> None:
        with Http.fake() as fake:
            await Http.as_form().timeout(5).post("https://x.test/f", {"k": "v"})
        assert fake.recorded[0].method == "POST"


class TestVerbs:
    async def test_head_put_patch_delete(self) -> None:
        with Http.fake() as fake:
            await Http.head("https://x.test/h")
            await Http.put("https://x.test/p", {"a": 1})
            await Http.patch("https://x.test/q", {"b": 2})
            await Http.delete("https://x.test/d")
        methods = [r.method for r in fake.recorded]
        assert methods == ["HEAD", "PUT", "PATCH", "DELETE"]

    async def test_recorded_returns_sent_requests(self) -> None:
        with Http.fake():
            await Http.get("https://x.test/r")
            recorded = Http.recorded()
        assert len(recorded) == 1
        assert recorded[0].url == "https://x.test/r"


class TestFakeRecording:
    async def test_records_method_url_and_data(self) -> None:
        with Http.fake() as fake:
            await Http.post("https://x.test/y", {"name": "ada"})
        assert len(fake.recorded) == 1
        rec = fake.recorded[0]
        assert rec.method == "POST"
        assert rec.url == "https://x.test/y"
        assert rec.data == {"name": "ada"}

    async def test_with_token_sets_authorization_header(self) -> None:
        with Http.fake() as fake:
            await Http.with_token("abc123").get("https://x.test/me")
        assert fake.recorded[0].has_header("Authorization", "Bearer abc123")

    async def test_query_params_recorded(self) -> None:
        with Http.fake() as fake:
            await Http.get("https://x.test/s", {"q": "term"})
        assert fake.recorded[0].params == {"q": "term"}


class TestAssertions:
    async def test_assert_sent_and_count(self) -> None:
        with Http.fake():
            await Http.get("https://x.test/a")
            await Http.get("https://x.test/b")
            Http.assert_sent(lambda r: r.url.endswith("/a"))
            Http.assert_not_sent(lambda r: r.url.endswith("/zzz"))
            Http.assert_sent_count(2)

    async def test_assert_sent_failure(self) -> None:
        with Http.fake():
            await Http.get("https://x.test/a")
            with pytest.raises(AssertionError):
                Http.assert_sent(lambda r: r.method == "DELETE")

    async def test_assert_nothing_sent(self) -> None:
        with Http.fake():
            Http.assert_nothing_sent()

    async def test_assert_not_sent_failure(self) -> None:
        with Http.fake():
            await Http.get("https://x.test/a")
            with pytest.raises(AssertionError):
                Http.assert_not_sent(lambda r: r.url.endswith("/a"))

    async def test_assert_sent_count_mismatch(self) -> None:
        with Http.fake():
            await Http.get("https://x.test/a")
            with pytest.raises(AssertionError, match="Expected 2 sent"):
                Http.assert_sent_count(2)

    async def test_assert_nothing_sent_failure(self) -> None:
        with Http.fake():
            await Http.get("https://x.test/a")
            with pytest.raises(AssertionError, match="Expected no requests"):
                Http.assert_nothing_sent()

    def test_assertions_require_fake_context(self) -> None:
        with pytest.raises(TypeError, match="requires an active Http.fake"):
            Http.assert_nothing_sent()


class TestFakeIsolation:
    async def test_fake_resets_after_context(self) -> None:
        from arvel.http.client import active_fake

        with Http.fake():
            assert active_fake() is not None
        assert active_fake() is None
