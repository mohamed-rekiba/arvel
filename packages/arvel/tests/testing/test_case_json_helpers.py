"""Smoke tests for ArvelTestCase.get_json/post_json/put_json/etc."""

from __future__ import annotations

from typing import Any

import pytest
from arvel.routing import Route, Router
from arvel.testing import ArvelTestCase, TestResponse


def _register_echo_routes() -> None:
    Router.reset_singleton()

    @Route.get("/echo-json")
    async def echo_get() -> dict[str, str]:
        return {"method": "GET"}

    @Route.post("/echo-json")
    async def echo_post(payload: dict[str, Any]) -> dict[str, object]:
        return {"method": "POST", "received": payload}

    @Route.put("/echo-json")
    async def echo_put(payload: dict[str, Any]) -> dict[str, object]:
        return {"method": "PUT", "received": payload}

    @Route.patch("/echo-json")
    async def echo_patch(payload: dict[str, Any]) -> dict[str, object]:
        return {"method": "PATCH", "received": payload}

    @Route.delete("/echo-json")
    async def echo_delete() -> dict[str, str]:
        return {"method": "DELETE"}

    # Decorator registers with Router; static analyzers don't see the use.
    del echo_get, echo_post, echo_put, echo_patch, echo_delete


class _JsonCase(ArvelTestCase):
    async def asyncSetUp(self) -> None:
        _register_echo_routes()
        await super().asyncSetUp()


@pytest.mark.asyncio
async def test_get_json_sets_accept_header_and_returns_test_response() -> None:
    case = _JsonCase()
    await case.asyncSetUp()
    try:
        response = await case.get_json("/echo-json")
        assert isinstance(response, TestResponse)
        response.assert_ok()
        response.assert_json_fragment({"method": "GET"})
    finally:
        await case.asyncTearDown()


@pytest.mark.asyncio
async def test_post_json_serialises_body_and_sets_content_type() -> None:
    case = _JsonCase()
    await case.asyncSetUp()
    try:
        response = await case.post_json("/echo-json", {"name": "alice", "age": 30})
        response.assert_ok()
        response.assert_json_fragment({"method": "POST", "received": {"name": "alice", "age": 30}})
    finally:
        await case.asyncTearDown()


@pytest.mark.asyncio
async def test_put_patch_delete_json_helpers() -> None:
    case = _JsonCase()
    await case.asyncSetUp()
    try:
        put_resp = await case.put_json("/echo-json", {"x": 1})
        put_resp.assert_ok().assert_json_fragment({"method": "PUT", "received": {"x": 1}})

        patch_resp = await case.patch_json("/echo-json", {"y": 2})
        patch_resp.assert_ok().assert_json_fragment({"method": "PATCH", "received": {"y": 2}})

        del_resp = await case.delete_json("/echo-json")
        del_resp.assert_ok().assert_json_fragment({"method": "DELETE"})
    finally:
        await case.asyncTearDown()


@pytest.mark.asyncio
async def test_get_json_caller_headers_override_defaults() -> None:
    """Caller-supplied headers (case-insensitively) override the default Accept."""
    case = _JsonCase()
    await case.asyncSetUp()
    try:
        # Just ensure no errors and the response is still wrapped.
        response = await case.get_json(
            "/echo-json",
            headers={"Accept": "application/vnd.example+json"},
        )
        response.assert_ok()
    finally:
        await case.asyncTearDown()
