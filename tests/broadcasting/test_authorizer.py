"""Tests for ChannelAuthorizer — FR-005, FR-006.

FR-005: Channel authorization with callback registry.
FR-006: Auth endpoint for client-side channel auth.
SEC-001: Private/presence channels require auth.
SEC-002: Reuses AuthContext.
"""

from __future__ import annotations

from typing import Any

from arvel.auth.policy import AuthContext
from arvel.broadcasting.channels import Channel, PresenceChannel, PrivateChannel


def _make_auth_context(sub: str = "user-1", **kwargs: Any) -> AuthContext:
    return AuthContext(user=None, sub=sub, **kwargs)


class TestChannelAuthorizer:
    """FR-005: Callback-based channel authorization."""

    async def test_public_channel_always_authorized(self) -> None:
        from arvel.broadcasting.authorizer import ChannelAuthorizer

        auth = ChannelAuthorizer()
        ctx = _make_auth_context()
        result = await auth.authorize(ctx, Channel("news"))
        assert result is True

    async def test_private_channel_authorized_when_callback_returns_true(self) -> None:
        from arvel.broadcasting.authorizer import ChannelAuthorizer

        auth = ChannelAuthorizer()
        auth.private("orders.{user_id}", lambda ctx, user_id: ctx.sub == user_id)

        ctx = _make_auth_context(sub="42")
        result = await auth.authorize(ctx, PrivateChannel("orders.42"))
        assert result is True

    async def test_private_channel_denied_when_callback_returns_false(self) -> None:
        from arvel.broadcasting.authorizer import ChannelAuthorizer

        auth = ChannelAuthorizer()
        auth.private("orders.{user_id}", lambda ctx, user_id: ctx.sub == user_id)

        ctx = _make_auth_context(sub="99")
        result = await auth.authorize(ctx, PrivateChannel("orders.42"))
        assert result is False

    async def test_presence_channel_returns_user_metadata(self) -> None:
        from arvel.broadcasting.authorizer import ChannelAuthorizer

        auth = ChannelAuthorizer()
        auth.presence(
            "chat.{room_id}",
            lambda ctx, room_id: {"id": ctx.sub, "name": "Alice"},
        )

        ctx = _make_auth_context(sub="u1")
        result = await auth.authorize(ctx, PresenceChannel("chat.1"))
        assert result == {"id": "u1", "name": "Alice"}

    async def test_presence_channel_denied_when_callback_returns_none(self) -> None:
        from arvel.broadcasting.authorizer import ChannelAuthorizer

        auth = ChannelAuthorizer()
        auth.presence("chat.{room_id}", lambda ctx, room_id: None)

        ctx = _make_auth_context()
        result = await auth.authorize(ctx, PresenceChannel("chat.1"))
        assert result is None

    async def test_unregistered_private_channel_denied(self) -> None:
        from arvel.broadcasting.authorizer import ChannelAuthorizer

        auth = ChannelAuthorizer()
        ctx = _make_auth_context()
        result = await auth.authorize(ctx, PrivateChannel("secret.123"))
        assert result is False

    async def test_pattern_extracts_multiple_params(self) -> None:
        from arvel.broadcasting.authorizer import ChannelAuthorizer

        auth = ChannelAuthorizer()
        captured: dict[str, str] = {}

        def cb(ctx: AuthContext, org_id: str, team_id: str) -> bool:
            captured["org_id"] = org_id
            captured["team_id"] = team_id
            return True

        auth.private("org.{org_id}.team.{team_id}", cb)

        ctx = _make_auth_context()
        result = await auth.authorize(ctx, PrivateChannel("org.acme.team.42"))
        assert result is True
        assert captured == {"org_id": "acme", "team_id": "42"}
