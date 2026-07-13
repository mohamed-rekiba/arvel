"""arvel.client — the ``FakeResponse.to_httpx`` bytes branch and the ``RecordedRequest``
accessors (method/url/headers/content/json, incl. the invalid-JSON default)."""

from __future__ import annotations

import httpx

from arvel.client import FakeResponse, RecordedRequest


def test_fake_response_bytes_body() -> None:
    resp = FakeResponse(body=b"raw-bytes", status=201, headers={"x-k": "v"}).to_httpx()
    assert resp.status_code == 201
    assert resp.content == b"raw-bytes"
    assert resp.headers["x-k"] == "v"


def test_recorded_request_accessors_and_json() -> None:
    raw = httpx.Request("POST", "https://api.test/v1/items?a=1", json={"name": "widget", "qty": 3})
    rec = RecordedRequest(raw)
    assert rec.method == "POST"
    assert rec.url == "https://api.test/v1/items?a=1"
    assert rec.headers["content-type"] == "application/json"
    assert rec.content == raw.content
    assert rec.json() == {"name": "widget", "qty": 3}
    assert rec.json("name") == "widget"
    assert rec.json("missing", default="fallback") == "fallback"


def test_recorded_request_json_on_invalid_body_returns_default() -> None:
    raw = httpx.Request("POST", "https://api.test/x", content=b"not-json")
    rec = RecordedRequest(raw)
    assert rec.json(default="dflt") == "dflt"
