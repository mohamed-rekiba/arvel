"""FR-013-023, NFR-013-008 — BroadcastAuthController (HTTP endpoint)."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_auth_controller_signs_for_authorized_user() -> None:
    """FR-013-023 AC1: returns signed auth payload for authorized channel."""
    from arvel.broadcasting.channels import ChannelRegistry
    from arvel.broadcasting.config import BroadcastConfig, ReverbConfig
    from arvel.reverb.auth_controller import BroadcastAuthController

    registry = ChannelRegistry()

    async def _cb(user: object, id: str) -> bool:
        return True

    registry.register("private-x.{id}", _cb)
    reverb = ReverbConfig(app_id="a", key="k", secret="s")
    controller = BroadcastAuthController(
        registry=registry,
        config=BroadcastConfig(),
        reverb=reverb,
    )
    result = await controller.handle(
        socket_id="1.2",
        channel="private-x.5",
        user="alice",
    )
    assert result is not None
    assert "auth" in result
    assert result["auth"].startswith("k:")


@pytest.mark.asyncio
async def test_auth_controller_rejects_unauthorized() -> None:
    """FR-013-023 AC2: unauthorized user → 403-equivalent (returns None / raises)."""
    from arvel.broadcasting.channels import ChannelRegistry
    from arvel.broadcasting.config import BroadcastConfig, ReverbConfig
    from arvel.broadcasting.exceptions import BroadcastAuthError
    from arvel.reverb.auth_controller import BroadcastAuthController

    registry = ChannelRegistry()

    async def _cb(user: object, id: str) -> bool:
        return False

    registry.register("private-x.{id}", _cb)
    reverb = ReverbConfig(app_id="a", key="k", secret="s")
    controller = BroadcastAuthController(
        registry=registry,
        config=BroadcastConfig(),
        reverb=reverb,
    )
    with pytest.raises(BroadcastAuthError):
        await controller.handle(socket_id="1.2", channel="private-x.5", user="bob")


@pytest.mark.asyncio
async def test_auth_controller_handles_presence_channel() -> None:
    """FR-013-023 AC3: presence channel returns channel_data + auth."""
    from arvel.broadcasting.channels import ChannelRegistry
    from arvel.broadcasting.config import BroadcastConfig, ReverbConfig
    from arvel.reverb.auth_controller import BroadcastAuthController

    registry = ChannelRegistry()

    async def _cb(user: object, id: str) -> dict[str, object]:
        return {"id": "u-42", "info": {"name": "Alice"}}

    registry.register("presence-room.{id}", _cb)
    reverb = ReverbConfig(app_id="a", key="k", secret="s")
    controller = BroadcastAuthController(
        registry=registry,
        config=BroadcastConfig(),
        reverb=reverb,
    )
    result = await controller.handle(
        socket_id="1.2",
        channel="presence-room.7",
        user="alice",
    )
    assert result is not None
    assert "channel_data" in result
    assert "auth" in result


@pytest.mark.asyncio
async def test_auth_controller_logs_failures(caplog: pytest.LogCaptureFixture) -> None:
    """NFR-013-008 AC2: every rejection emits a structured log event."""
    from arvel.broadcasting.channels import ChannelRegistry
    from arvel.broadcasting.config import BroadcastConfig, ReverbConfig
    from arvel.broadcasting.exceptions import BroadcastAuthError
    from arvel.reverb.auth_controller import BroadcastAuthController

    registry = ChannelRegistry()

    async def _cb(user: object, id: str) -> bool:
        return False

    registry.register("private-x.{id}", _cb)
    reverb = ReverbConfig(app_id="a", key="k", secret="s")
    controller = BroadcastAuthController(
        registry=registry,
        config=BroadcastConfig(),
        reverb=reverb,
    )

    with caplog.at_level("WARNING"), pytest.raises(BroadcastAuthError):
        await controller.handle(socket_id="1.2", channel="private-x.5", user="bob")
    assert any("broadcast_auth_rejected" in r.message for r in caplog.records)
