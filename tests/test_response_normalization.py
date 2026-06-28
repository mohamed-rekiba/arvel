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
