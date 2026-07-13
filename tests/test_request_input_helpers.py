"""Request convenience accessors: bearer_token / input / boolean (round H7)."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.http.request import Request


class _Raw:
    def __init__(self, headers: dict[str, str], body: Any, query: dict[str, str]) -> None:
        self.headers = headers
        self._body = body
        self.query_params = query

    async def json(self) -> Any:
        return self._body


def _req(
    headers: dict[str, str] | None = None, body: Any = None, query: dict[str, str] | None = None
) -> Request:
    return Request(_Raw(headers or {}, body if body is not None else {}, query or {}))


def test_bearer_token() -> None:
    assert _req({"authorization": "Bearer abc.def"}).bearer_token() == "abc.def"
    assert _req({"authorization": "bearer xyz"}).bearer_token() == "xyz"  # case-insensitive scheme
    assert _req({"authorization": "Basic zzz"}).bearer_token() is None
    assert _req({}).bearer_token() is None


@pytest.mark.asyncio
async def test_input_prefers_body_then_query() -> None:
    r = _req(body={"a": 1}, query={"b": "2"})
    assert await r.input("a") == 1
    assert await r.input("b") == "2"
    assert await r.input("missing", "d") == "d"


class _RaisingRaw(_Raw):
    async def json(self) -> Any:  # a non-JSON (e.g. form) body raises when parsed as JSON
        raise ValueError("not json")


@pytest.mark.asyncio
async def test_input_falls_back_to_query_when_body_is_not_json() -> None:
    r = Request(_RaisingRaw({}, None, {"q": "x"}))
    assert await r.input("q") == "x"  # no crash; query fallback
    assert await r.boolean("flag", default=True) is True


@pytest.mark.asyncio
async def test_boolean_coercion() -> None:
    for truthy in ("1", "true", "TRUE", "on", "yes"):
        assert await _req(body={"f": truthy}).boolean("f") is True
    for falsy in ("0", "false", "no", "off", ""):
        assert await _req(body={"f": falsy}).boolean("f") is False
    assert await _req(body={}).boolean("f", default=True) is True
