"""Tests for CSRF protection middleware."""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from arvel.security.csrf import CsrfMiddleware, generate_csrf_token, verify_csrf_token

if TYPE_CHECKING:
    from starlette.requests import Request

SECRET_KEY = b"test-secret-key-for-csrf-testing"


class TestTokenGeneration:
    def test_generate_returns_signed_token(self) -> None:
        token = generate_csrf_token(SECRET_KEY)
        assert "." in token
        parts = token.split(".")
        assert len(parts) == 2
        assert len(parts[0]) == 64  # 32 bytes hex
        assert len(parts[1]) == 64  # sha256 hex

    def test_verify_valid_token(self) -> None:
        token = generate_csrf_token(SECRET_KEY)
        assert verify_csrf_token(token, SECRET_KEY) is True

    def test_verify_tampered_token(self) -> None:
        token = generate_csrf_token(SECRET_KEY)
        tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
        assert verify_csrf_token(tampered, SECRET_KEY) is False

    def test_verify_wrong_key(self) -> None:
        token = generate_csrf_token(SECRET_KEY)
        assert verify_csrf_token(token, b"wrong-key") is False

    def test_verify_malformed_token(self) -> None:
        assert verify_csrf_token("no-dot-here", SECRET_KEY) is False

    def test_each_token_is_unique(self) -> None:
        tokens = {generate_csrf_token(SECRET_KEY) for _ in range(10)}
        assert len(tokens) == 10


async def _echo_handler(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def _create_app(
    exclude_paths: set[str] | None = None,
    exclude_prefixes: tuple[str, ...] = (),
    allowed_origins: set[str] | None = None,
) -> Starlette:
    app = Starlette(
        routes=[
            Route("/submit", _echo_handler, methods=["POST"]),
            Route("/read", _echo_handler, methods=["GET"]),
            Route("/api/data", _echo_handler, methods=["POST"]),
        ],
    )
    app.add_middleware(
        CsrfMiddleware,
        secret_key=SECRET_KEY,
        exclude_paths=exclude_paths,
        exclude_prefixes=exclude_prefixes,
        allowed_origins=allowed_origins,
    )
    return app


class TestCsrfMiddleware:
    def test_get_requests_pass_through(self) -> None:
        client = TestClient(_create_app())
        resp = client.get("/read")
        assert resp.status_code == 200

    def test_post_without_token_returns_419(self) -> None:
        client = TestClient(_create_app())
        resp = client.post("/submit", json={"data": "test"})
        assert resp.status_code == 419
        body = resp.json()
        assert body["error"]["code"] == "CSRF_TOKEN_MISMATCH"

    def test_post_with_valid_token_passes(self) -> None:
        client = TestClient(_create_app())
        token = generate_csrf_token(SECRET_KEY)
        resp = client.post("/submit", json={"data": "test"}, headers={"X-CSRF-Token": token})
        assert resp.status_code == 200

    def test_post_with_invalid_token_returns_419(self) -> None:
        client = TestClient(_create_app())
        resp = client.post("/submit", json={"data": "test"}, headers={"X-CSRF-Token": "bad.token"})
        assert resp.status_code == 419

    def test_excluded_path_skips_check(self) -> None:
        client = TestClient(_create_app(exclude_paths={"/submit"}))
        resp = client.post("/submit", json={"data": "test"})
        assert resp.status_code == 200

    def test_excluded_prefix_skips_check(self) -> None:
        client = TestClient(_create_app(exclude_prefixes=("/api/",)))
        resp = client.post("/api/data", json={"data": "test"})
        assert resp.status_code == 200

    def test_allowed_origin_passes(self) -> None:
        client = TestClient(_create_app(allowed_origins={"https://app.example.com"}))
        resp = client.post(
            "/submit",
            json={"data": "test"},
            headers={"Origin": "https://app.example.com"},
        )
        assert resp.status_code == 200

    def test_disallowed_origin_without_token_returns_419(self) -> None:
        client = TestClient(_create_app(allowed_origins={"https://app.example.com"}))
        resp = client.post(
            "/submit",
            json={"data": "test"},
            headers={"Origin": "https://evil.com"},
        )
        assert resp.status_code == 419
