"""ClientResponse — the typed wrapper (spec 07 §2): predicates, dotted json(), throw() chain."""

from __future__ import annotations

import httpx
import pytest

from arvel.client import ClientResponse, RequestFailed


def _response(status: int, **kwargs: object) -> ClientResponse:
    return ClientResponse(httpx.Response(status, **kwargs))  # type: ignore[arg-type]


def test_200_is_ok_and_successful_not_failed() -> None:
    response = _response(200, json={"id": 1})
    assert response.status() == 200
    assert response.ok() is True
    assert response.successful() is True
    assert response.failed() is False
    assert response.client_error() is False
    assert response.server_error() is False
    assert response.redirect() is False
    assert response.json() == {"id": 1}


def test_ok_means_exactly_200_not_the_whole_2xx_range() -> None:
    for status in (201, 202, 204):
        response = _response(status)
        assert response.ok() is False  # ok() is 200 exactly
        assert response.successful() is True  # successful() is any 2xx


def test_content_returns_raw_bytes_not_decoded_text() -> None:
    """``content()`` is the raw bytes (for images/files); ``body()`` is the lossy text decode."""
    binary = b"\x89PNG\r\n\x1a\n\x00\xff\xfe raw"
    response = _response(200, content=binary)
    assert response.content() == binary
    assert isinstance(response.content(), bytes)


def test_404_is_a_client_error_and_failed() -> None:
    response = _response(404)
    assert response.client_error() is True
    assert response.failed() is True
    assert response.successful() is False


def test_500_is_a_server_error_and_failed() -> None:
    response = _response(500)
    assert response.server_error() is True
    assert response.failed() is True


def test_3xx_is_a_redirect() -> None:
    response = _response(302, headers={"Location": "/elsewhere"})
    assert response.redirect() is True
    assert response.header("Location") == "/elsewhere"
    assert response.header("Nope") is None


def test_body_returns_text() -> None:
    response = _response(200, text="hello")
    assert response.body() == "hello"


def test_json_with_dotted_key_and_default() -> None:
    response = _response(200, json={"user": {"name": "Ada", "roles": ["admin", "owner"]}})
    assert response.json("user.name") == "Ada"
    assert response.json("user.roles.1") == "owner"
    assert response.json("user.missing", "fallback") == "fallback"
    assert response.json("user.name.nested", "fallback") == "fallback"


def test_json_default_when_body_is_not_json() -> None:
    response = _response(200, text="not json")
    assert response.json(default={"empty": True}) == {"empty": True}


def test_throw_is_a_noop_on_2xx_and_chainable() -> None:
    response = _response(200, json={"ok": True})
    assert response.throw() is response
    assert response.throw().json() == {"ok": True}


def test_throw_raises_request_failed_on_4xx_and_5xx() -> None:
    response = _response(404)
    with pytest.raises(RequestFailed) as exc_info:
        response.throw()
    assert exc_info.value.response is response
    assert "404" in str(exc_info.value)


def test_raw_is_the_httpx_response_escape_hatch() -> None:
    response = _response(200)
    assert isinstance(response.raw, httpx.Response)
    assert isinstance(response.headers(), httpx.Headers)
