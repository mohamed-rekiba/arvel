"""HTTP (doc 04) — response normalization: every handler return becomes a Litestar Response."""

from __future__ import annotations

from typing import Any

import litestar
from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.http.middleware import Middleware

SEEN: list[str] = []


class Recorder(Middleware):
    async def terminate(self, request: Any, response: Any) -> None:
        # the payoff: even a plain-dict handler return arrives here as a Litestar Response
        SEEN.append(type(response).__name__)


def test_dict_return_is_normalized_and_seen_as_response_by_terminate() -> None:
    SEEN.clear()
    kernel = HttpKernel()
    kernel.global_middleware = [Recorder]
    kernel.get("/", lambda request: {"ok": True})
    with TestClient(kernel.build()) as client:
        r = client.get("/")
        assert r.status_code == 200
        assert r.json() == {"ok": True}
    assert SEEN == ["Response"]  # a litestar.Response, not a dict
    assert issubclass(litestar.Response, litestar.Response)  # sanity


def test_post_keeps_litestar_method_status_201() -> None:
    kernel = HttpKernel()
    kernel.post("/things", lambda request: {"created": True})
    with TestClient(kernel.build()) as client:
        r = client.post("/things", json={})
    assert r.status_code == 201  # normalization didn't clobber the method-aware default
    assert r.json() == {"created": True}


def test_none_return_is_a_response() -> None:
    kernel = HttpKernel()
    kernel.get("/empty", lambda request: None)
    with TestClient(kernel.build()) as client:
        assert client.get("/empty").status_code in (200, 204)  # a real response, no crash


def test_date_value_serializes_to_iso_string() -> None:
    # arvel Date must serialize to ISO in a response, not raise SerializationException.
    from arvel.dates import Date

    when = Date.now()
    kernel = HttpKernel()
    kernel.get("/d", lambda request: {"at": when})
    with TestClient(kernel.build()) as client:
        r = client.get("/d")
        assert r.status_code == 200
        assert r.json() == {"at": when.to_iso()}


def test_paginator_return_serializes_to_laravel_shape() -> None:
    from arvel.pagination import LengthAwarePaginator

    def handler(request: Any) -> Any:
        return LengthAwarePaginator([{"id": 1}, {"id": 2}], total=5, per_page=2, current_page=1)

    kernel = HttpKernel()
    kernel.get("/items", handler)
    with TestClient(kernel.build()) as client:
        d = client.get("/items").json()
    assert d["total"] == 5 and d["last_page"] == 3 and d["per_page"] == 2
    assert d["data"] == [{"id": 1}, {"id": 2}]
    assert d["current_page"] == 1 and d["next_page_url"].endswith("page=2")
