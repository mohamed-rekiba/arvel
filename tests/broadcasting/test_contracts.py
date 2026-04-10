"""Tests for BroadcastContract — FR-001.

FR-001: BroadcastContract ABC with broadcast(channels, event, data).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from arvel.broadcasting.contracts import BroadcastContract

if TYPE_CHECKING:
    from arvel.broadcasting.channels import Channel


class TestBroadcastContract:
    """FR-001: Contract is an ABC that can't be instantiated directly."""

    def test_contract_is_abstract(self) -> None:
        with pytest.raises(TypeError, match="abstract"):
            BroadcastContract()  # type: ignore[abstract]

    def test_concrete_implementation_satisfies_contract(self) -> None:
        class StubBroadcaster(BroadcastContract):
            async def broadcast(
                self,
                channels: list[Channel],
                event: str,
                data: dict[str, Any],
            ) -> None:
                pass

        broadcaster = StubBroadcaster()
        assert isinstance(broadcaster, BroadcastContract)
