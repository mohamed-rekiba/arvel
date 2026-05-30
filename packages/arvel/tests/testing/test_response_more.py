"""TestResponse assertion edges."""

from __future__ import annotations

import httpx
import pytest
from arvel.testing.response import TestResponse as ArvelTestResponse


def _response(
    status_code: int,
    content: bytes = b"",
    *,
    headers: dict[str, str] | None = None,
) -> ArvelTestResponse:
    request = httpx.Request("GET", "http://testserver")
    return ArvelTestResponse(
        httpx.Response(status_code, content=content, headers=headers, request=request)
    )


def test_test_response_empty_json_and_status_helpers() -> None:
    response = _response(204)

    assert response.raw.status_code == 204
    assert response.status_code == 204
    assert response.json() is None
    assert response.assert_ok() is response


def test_test_response_failure_helpers_raise_clear_assertions() -> None:
    with pytest.raises(AssertionError, match="expected 2xx"):
        _response(500, b"server error").assert_ok()
    with pytest.raises(AssertionError, match="expected status 404"):
        _response(200).assert_not_found()
    with pytest.raises(AssertionError, match="expected 3xx redirect"):
        _response(200).assert_redirect()
    with pytest.raises(AssertionError, match="expected redirect"):
        _response(302, headers={"Location": "/other"}).assert_redirect("/target")


def test_test_response_json_header_cookie_edges() -> None:
    response = _response(
        200,
        b'{"data": [{"name": "Ada"}]}',
        headers={"X-Test": "ok", "set-cookie": "session=abc"},
    )

    assert response.assert_json({"data": [{"name": "Ada"}]}) is response
    assert response.assert_json_path("data.0.name", "Ada") is response
    assert response.assert_header("X-Test", "ok") is response
    assert response.assert_cookie("session") is response

    with pytest.raises(AssertionError, match="json mismatch"):
        response.assert_json({"data": []})
    with pytest.raises(AssertionError, match="not found"):
        response.assert_json_path("data.one.name", "Ada")
    with pytest.raises(AssertionError, match="expected 'bad'"):
        response.assert_header("X-Test", "bad")
    with pytest.raises(AssertionError, match="cookie"):
        response.assert_cookie("missing")
