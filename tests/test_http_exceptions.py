"""C4b — FormRequest validation wiring + content-negotiated exception rendering."""

from __future__ import annotations

from typing import Any

from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.validation import FormRequest


class CreateUser(FormRequest):
    name: str
    age: int


class GuardedForm(FormRequest):
    value: int

    def authorize(self) -> bool:
        return False


async def _store(request: Any) -> dict[str, Any]:
    form = await request.validate(CreateUser)
    return {"name": form.name, "age": form.age}


async def _guarded(request: Any) -> dict[str, Any]:
    await request.validate(GuardedForm)
    return {"ok": True}


def _client() -> TestClient[Any]:
    kernel = HttpKernel()
    kernel.post("/users", _store)
    kernel.post("/guarded", _guarded)
    return TestClient(kernel.build())


def test_valid_form_passes() -> None:
    with _client() as client:
        response = client.post("/users", json={"name": "ada", "age": 36})
    assert response.status_code == 201
    assert response.json() == {"name": "ada", "age": 36}


def test_invalid_form_renders_422_json() -> None:
    with _client() as client:
        response = client.post(
            "/users", json={"name": "ada"}, headers={"accept": "application/json"}
        )
    assert response.status_code == 422
    body = response.json()
    assert body["message"] == "Unprocessable Entity"
    assert "errors" in body


def test_invalid_form_redirects_back_for_browser() -> None:
    # web clients (text/html) get a redirect-back, not a JSON 422 (doc 10 content negotiation)
    with _client() as client:
        response = client.post(
            "/users",
            json={"name": "ada"},
            headers={"accept": "text/html"},
            follow_redirects=False,
        )
    assert response.status_code == 302
    assert "location" in response.headers


def test_failed_authorize_renders_403() -> None:
    with _client() as client:
        response = client.post("/guarded", json={"value": 1})
    assert response.status_code == 403


def test_failed_authorize_renders_403_json_message_not_a_redirect() -> None:
    # H15 render-neutral: AuthorizationException still renders like the old ValidationException(403)
    # did — a JSON {message} body, never the 419/422 "return to the form" redirect-back.
    with _client() as client:
        response = client.post(
            "/guarded", json={"value": 1}, headers={"accept": "application/json"}
        )
    assert response.status_code == 403
    assert response.json()["message"]


def test_failed_authorize_renders_403_html_page_for_a_browser_client() -> None:
    with _client() as client:
        response = client.post(
            "/guarded",
            json={"value": 1},
            headers={"accept": "text/html"},
            follow_redirects=False,
        )
    assert response.status_code == 403  # not a 302 — 403 isn't in the redirect-back status set
    assert "html" in response.headers["content-type"]


def test_same_origin_or_root_blocks_backslash_open_redirect() -> None:
    from arvel.http.exceptions import same_origin_or_root

    # browsers normalize a leading backslash to "/", turning these into off-host
    # protocol-relative redirects — the guard must treat them as external.
    assert same_origin_or_root("/\\evil.com", "app.test") == "/"
    assert same_origin_or_root("\\/evil.com", "app.test") == "/"
    assert same_origin_or_root("//evil.com", "app.test") == "/"
    # genuinely same-origin / relative targets still pass through
    assert same_origin_or_root("/dashboard", "app.test") == "/dashboard"
    assert same_origin_or_root("https://app.test/x", "app.test") == "https://app.test/x"
