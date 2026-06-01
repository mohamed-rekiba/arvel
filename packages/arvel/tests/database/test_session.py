"""Request-scoped session context var."""

from __future__ import annotations

from typing import Any, cast

import pytest
from arvel.database.session import (
    NoActiveSessionError,
    get_active_session,
    reset_active_session,
    set_active_session,
    use_session,
)
from sqlalchemy.ext.asyncio import AsyncSession


def test_no_active_session_raises() -> None:
    with pytest.raises(NoActiveSessionError):
        get_active_session()


async def test_use_session_context_manager_binds_and_unbinds(
    session: Any,
) -> None:
    # `session` fixture already binds via set_active_session, so it's active.
    bound = get_active_session()
    assert bound is session

    sentinel = cast("AsyncSession", object())
    async with use_session(sentinel):
        assert get_active_session() is sentinel
    # After the context exits, the prior session is restored.
    assert get_active_session() is session


def test_set_reset_via_token() -> None:
    sentinel = cast("AsyncSession", object())
    token = set_active_session(sentinel)
    try:
        assert get_active_session() is sentinel
    finally:
        reset_active_session(token)
