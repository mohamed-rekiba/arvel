"""Tests for BroadcastServiceProvider — FR-010.

FR-010: Provider registers BroadcastContract and ChannelAuthorizer.
"""

from __future__ import annotations


class TestBroadcastServiceProvider:
    """FR-010: Provider wires broadcasting into the DI container."""

    async def test_provider_registers_broadcast_contract(self) -> None:
        from arvel.broadcasting.contracts import BroadcastContract
        from arvel.broadcasting.provider import BroadcastServiceProvider
        from arvel.foundation.container import ContainerBuilder

        builder = ContainerBuilder()
        provider = BroadcastServiceProvider()
        await provider.register(builder)

        container = builder.build()
        broadcaster = await container.resolve(BroadcastContract)
        assert isinstance(broadcaster, BroadcastContract)

    async def test_provider_registers_channel_authorizer(self) -> None:
        from arvel.broadcasting.authorizer import ChannelAuthorizer
        from arvel.broadcasting.provider import BroadcastServiceProvider
        from arvel.foundation.container import ContainerBuilder

        builder = ContainerBuilder()
        provider = BroadcastServiceProvider()
        await provider.register(builder)

        container = builder.build()
        authorizer = await container.resolve(ChannelAuthorizer)
        assert isinstance(authorizer, ChannelAuthorizer)
