"""FR-013-011 + FR-013-012 — ChannelRegistry pattern matching and authorization."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
def registry() -> Any:
    from arvel.broadcasting.channels import ChannelRegistry

    return ChannelRegistry()


def test_register_returns_self_for_chaining(registry: Any) -> None:
    async def _cb(user: Any, id: str) -> bool:
        return True

    result = registry.register("private-user.{id}", _cb)
    assert result is registry


@pytest.mark.asyncio
async def test_match_resolves_placeholders(registry: Any) -> None:
    """FR-013-011 AC2: {id} placeholders are extracted and passed as kwargs."""
    captured: dict[str, Any] = {}

    async def _cb(user: Any, id: str) -> bool:
        captured["user"] = user
        captured["id"] = id
        return True

    registry.register("private-user.{id}", _cb)
    result = await registry.authorize("private-user.5", user="alice")
    assert result is True
    assert captured["id"] == "5"
    assert captured["user"] == "alice"


@pytest.mark.asyncio
async def test_first_match_wins(registry: Any) -> None:
    """FR-013-011 AC4: registration order is preserved; first match wins."""
    calls: list[str] = []

    async def _cb1(user: Any, id: str) -> bool:
        calls.append("one")
        return True

    async def _cb2(user: Any, id: str) -> bool:
        calls.append("two")
        return True

    registry.register("private-user.{id}", _cb1)
    registry.register("private-user.{id}", _cb2)
    await registry.authorize("private-user.5", user=None)
    assert calls == ["one"]


@pytest.mark.asyncio
async def test_no_match_returns_false(registry: Any) -> None:
    """FR-013-012 AC1: no callback registered → reject (return False)."""
    result = await registry.authorize("private-orphan.5", user="x")
    assert result is False


@pytest.mark.asyncio
async def test_callback_returning_falsy_rejects(registry: Any) -> None:
    """FR-013-012 AC2: callback returning False/None rejects."""

    async def _cb_false(user: Any, id: str) -> bool:
        return False

    registry.register("private-x.{id}", _cb_false)
    assert await registry.authorize("private-x.1", user="u") is False


@pytest.mark.asyncio
async def test_presence_channel_returns_presence_payload(registry: Any) -> None:
    """FR-013-012 AC4: presence channel callbacks may return a dict (presence payload)."""

    async def _cb(user: Any, id: str) -> dict[str, Any]:
        return {"id": "u-42", "info": {"name": "Alice"}}

    registry.register("presence-room.{id}", _cb)
    result = await registry.authorize("presence-room.7", user="alice")
    assert result == {"id": "u-42", "info": {"name": "Alice"}}


@pytest.mark.asyncio
async def test_callback_raising_returns_false_and_logs(registry: Any) -> None:
    """FR-013-012 AC3: raising callback authorize returns False (rejected)."""

    async def _cb_boom(user: Any, id: str) -> bool:
        raise ValueError("db down")

    registry.register("private-x.{id}", _cb_boom)
    result = await registry.authorize("private-x.1", user="u")
    assert result is False


def test_placeholder_does_not_match_dots(registry: Any) -> None:
    """ADR-054: {id} matches [^./]+ — does not span path separators."""
    from arvel.broadcasting.channels import compile_pattern

    pattern = compile_pattern("private-user.{id}")
    # ID may not contain "." or "/"
    assert pattern.fullmatch("private-user.5") is not None
    assert pattern.fullmatch("private-user.5.6") is None
    assert pattern.fullmatch("private-user.foo/bar") is None


def test_literal_dots_are_escaped(registry: Any) -> None:
    """ADR-054: literal dots in patterns are re-escaped to avoid regex meta-match."""
    from arvel.broadcasting.channels import compile_pattern

    pattern = compile_pattern("private-user.{id}")
    # Without escape, '.' would match any char including 'x'. With escape it's literal.
    assert pattern.fullmatch("private-userX5") is None
