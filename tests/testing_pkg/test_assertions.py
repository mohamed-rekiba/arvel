"""Tests for TestResponse HTTP assertions — Story 1, all 8 ACs."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse, RedirectResponse

from arvel.testing.assertions import TestResponse
from arvel.testing.client import TestClient


@pytest.fixture
def sample_app() -> FastAPI:
    app = FastAPI()

    @app.get("/users")
    async def list_users() -> dict:
        return {"data": {"users": [{"name": "Alice"}, {"name": "Bob"}]}}

    @app.get("/users/1")
    async def get_user() -> dict:
        return {"data": {"id": 1, "name": "Alice", "email": "alice@test.com"}}

    @app.post("/users", status_code=201)
    async def create_user() -> dict:
        return {"data": {"id": 2, "name": "Bob"}}

    @app.delete("/users/1", status_code=204)
    async def delete_user() -> None:
        return None

    @app.get("/not-found", status_code=404)
    async def not_found() -> dict:
        return {"error": {"code": "NOT_FOUND", "message": "Resource not found"}}

    @app.get("/redirect")
    async def redirect() -> RedirectResponse:
        return RedirectResponse(url="/login", status_code=302)

    @app.get("/with-headers")
    async def with_headers() -> JSONResponse:
        resp = JSONResponse({"ok": True})
        resp.headers["X-Request-Id"] = "req-123"
        resp.set_cookie("session_id", "abc")
        return resp

    @app.get("/empty")
    async def empty() -> dict:
        return {}

    @app.get("/invalid-json")
    async def invalid_json() -> JSONResponse:
        return JSONResponse(content="not json", media_type="text/plain")

    return app


class TestTestResponse:
    """AC-S1-1: assert_status passes on match, raises on mismatch."""

    @pytest.mark.anyio
    async def test_assert_status_passes(self, sample_app: FastAPI) -> None:
        async with TestClient(sample_app) as client:
            response = await client.get("/users")
            result = response.assert_status(200)
            assert isinstance(result, TestResponse)

    @pytest.mark.anyio
    async def test_assert_status_fails(self, sample_app: FastAPI) -> None:
        async with TestClient(sample_app) as client:
            response = await client.get("/users")
            with pytest.raises(AssertionError, match="Expected status 404"):
                response.assert_status(404)

    @pytest.mark.anyio
    async def test_assert_ok(self, sample_app: FastAPI) -> None:
        async with TestClient(sample_app) as client:
            response = await client.get("/users")
            response.assert_ok()

    @pytest.mark.anyio
    async def test_assert_created(self, sample_app: FastAPI) -> None:
        async with TestClient(sample_app) as client:
            response = await client.post("/users")
            response.assert_created()

    @pytest.mark.anyio
    async def test_assert_no_content(self, sample_app: FastAPI) -> None:
        async with TestClient(sample_app) as client:
            response = await client.delete("/users/1")
            response.assert_no_content()

    @pytest.mark.anyio
    async def test_assert_not_found(self, sample_app: FastAPI) -> None:
        async with TestClient(sample_app) as client:
            response = await client.get("/not-found")
            response.assert_not_found()


class TestAssertJson:
    """AC-S1-2: assert_json matches full response body."""

    @pytest.mark.anyio
    async def test_assert_json_match(self, sample_app: FastAPI) -> None:
        async with TestClient(sample_app) as client:
            response = await client.get("/users/1")
            response.assert_json({"data": {"id": 1, "name": "Alice", "email": "alice@test.com"}})

    @pytest.mark.anyio
    async def test_assert_json_mismatch(self, sample_app: FastAPI) -> None:
        async with TestClient(sample_app) as client:
            response = await client.get("/users/1")
            with pytest.raises(AssertionError, match="JSON body mismatch"):
                response.assert_json({"data": {"id": 999}})


class TestAssertJsonPath:
    """AC-S1-3: assert_json_path traverses dot-notation path."""

    @pytest.mark.anyio
    async def test_json_path_nested(self, sample_app: FastAPI) -> None:
        async with TestClient(sample_app) as client:
            response = await client.get("/users/1")
            response.assert_json_path("data.name", "Alice")

    @pytest.mark.anyio
    async def test_json_path_with_index(self, sample_app: FastAPI) -> None:
        async with TestClient(sample_app) as client:
            response = await client.get("/users")
            response.assert_json_path("data.users.0.name", "Alice")

    @pytest.mark.anyio
    async def test_json_path_mismatch(self, sample_app: FastAPI) -> None:
        async with TestClient(sample_app) as client:
            response = await client.get("/users/1")
            with pytest.raises(AssertionError, match=r"at path 'data\.name'"):
                response.assert_json_path("data.name", "Bob")

    @pytest.mark.anyio
    async def test_json_path_missing_key(self, sample_app: FastAPI) -> None:
        async with TestClient(sample_app) as client:
            response = await client.get("/users/1")
            with pytest.raises(AssertionError, match=r"Path 'data\.nonexistent' not found"):
                response.assert_json_path("data.nonexistent", "anything")


class TestAssertJsonStructure:
    """AC-S1-4: assert_json_structure validates keys exist."""

    @pytest.mark.anyio
    async def test_structure_match(self, sample_app: FastAPI) -> None:
        async with TestClient(sample_app) as client:
            response = await client.get("/users/1")
            response.assert_json_structure({"data": {"id": True, "name": True}})

    @pytest.mark.anyio
    async def test_structure_missing_key(self, sample_app: FastAPI) -> None:
        async with TestClient(sample_app) as client:
            response = await client.get("/users/1")
            with pytest.raises(AssertionError, match="Missing key"):
                response.assert_json_structure({"data": {"id": True, "role": True}})


class TestAssertJsonMissing:
    """AC-S1-5: assert_json_missing verifies key absent."""

    @pytest.mark.anyio
    async def test_json_missing_passes(self, sample_app: FastAPI) -> None:
        async with TestClient(sample_app) as client:
            response = await client.get("/users/1")
            response.assert_json_missing("password")

    @pytest.mark.anyio
    async def test_json_missing_fails(self, sample_app: FastAPI) -> None:
        async with TestClient(sample_app) as client:
            response = await client.get("/users/1")
            with pytest.raises(AssertionError, match="Key 'data' should not be present"):
                response.assert_json_missing("data")


class TestAssertRedirect:
    """AC-S1-6: assert_redirect checks 3xx + Location header."""

    @pytest.mark.anyio
    async def test_redirect_passes(self, sample_app: FastAPI) -> None:
        async with TestClient(sample_app) as client:
            client_raw = client._ensure_open()
            response_raw = await client_raw.get(
                "/redirect",
                headers=client._merge_headers(None),
                follow_redirects=False,
            )
            from arvel.testing.assertions import TestResponse

            response = TestResponse(response_raw)
            response.assert_redirect("/login")

    @pytest.mark.anyio
    async def test_redirect_without_url(self, sample_app: FastAPI) -> None:
        async with TestClient(sample_app) as client:
            client_raw = client._ensure_open()
            response_raw = await client_raw.get(
                "/redirect",
                headers=client._merge_headers(None),
                follow_redirects=False,
            )
            from arvel.testing.assertions import TestResponse

            response = TestResponse(response_raw)
            response.assert_redirect()

    @pytest.mark.anyio
    async def test_redirect_fails_on_200(self, sample_app: FastAPI) -> None:
        async with TestClient(sample_app) as client:
            response = await client.get("/users")
            with pytest.raises(AssertionError, match="Expected redirect"):
                response.assert_redirect()


class TestAssertHeader:
    """AC-S1-7: assert_header checks header presence and optional value."""

    @pytest.mark.anyio
    async def test_header_present(self, sample_app: FastAPI) -> None:
        async with TestClient(sample_app) as client:
            response = await client.get("/with-headers")
            response.assert_header("x-request-id")

    @pytest.mark.anyio
    async def test_header_with_value(self, sample_app: FastAPI) -> None:
        async with TestClient(sample_app) as client:
            response = await client.get("/with-headers")
            response.assert_header("x-request-id", "req-123")

    @pytest.mark.anyio
    async def test_header_missing(self, sample_app: FastAPI) -> None:
        async with TestClient(sample_app) as client:
            response = await client.get("/users")
            with pytest.raises(AssertionError, match="Header 'x-custom' not found"):
                response.assert_header("x-custom")


class TestAssertCookie:
    """AC-S1-8: assert_cookie checks cookie presence."""

    @pytest.mark.anyio
    async def test_cookie_present(self, sample_app: FastAPI) -> None:
        async with TestClient(sample_app) as client:
            response = await client.get("/with-headers")
            response.assert_cookie("session_id")

    @pytest.mark.anyio
    async def test_cookie_missing(self, sample_app: FastAPI) -> None:
        async with TestClient(sample_app) as client:
            response = await client.get("/users")
            with pytest.raises(AssertionError, match="Cookie 'token' not found"):
                response.assert_cookie("token")


class TestChaining:
    """Verify fluent chaining returns Self."""

    @pytest.mark.anyio
    async def test_chain_multiple_assertions(self, sample_app: FastAPI) -> None:
        async with TestClient(sample_app) as client:
            response = await client.get("/users/1")
            (
                response.assert_status(200)
                .assert_json_path("data.name", "Alice")
                .assert_json_missing("password")
            )


class TestClientReturnsTestResponse:
    """Verify TestClient methods return TestResponse."""

    @pytest.mark.anyio
    async def test_get_returns_test_response(self, sample_app: FastAPI) -> None:
        async with TestClient(sample_app) as client:
            response = await client.get("/users")
            assert isinstance(response, TestResponse)

    @pytest.mark.anyio
    async def test_post_returns_test_response(self, sample_app: FastAPI) -> None:
        async with TestClient(sample_app) as client:
            response = await client.post("/users")
            assert isinstance(response, TestResponse)


class TestErrorMessageTruncation:
    """SEC: Error messages truncated to prevent CI log leakage."""

    @pytest.mark.anyio
    async def test_error_message_truncated(self, sample_app: FastAPI) -> None:
        async with TestClient(sample_app) as client:
            response = await client.get("/users")
            try:
                response.assert_status(500)
            except AssertionError as e:
                assert len(str(e)) <= 600
