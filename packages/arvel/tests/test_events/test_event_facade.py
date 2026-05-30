"""Tests for Event facade — FR-009-010."""

from __future__ import annotations

import pytest
from arvel.events.event import Event
from arvel.events.listener import Listener


class _FacadeEvent(Event):
    tag: str


class TestEventFacade:
    def teardown_method(self) -> None:
        from arvel.facades.event import Event as EventFacade

        EventFacade.dispatcher = None

    def test_dispatch_raises_when_not_bound(self) -> None:
        import asyncio

        from arvel.facades.event import Event as EventFacade
        from arvel.queue.exceptions import FacadeNotBoundError

        with pytest.raises(FacadeNotBoundError):
            asyncio.run(EventFacade.dispatch(_FacadeEvent(tag="x")))

    @pytest.mark.asyncio
    async def test_dispatch_proxies_to_dispatcher(self) -> None:
        from arvel.events.dispatcher import EventDispatcher
        from arvel.facades.event import Event as EventFacade

        dispatcher = EventDispatcher()
        seen: list[str] = []

        class Cap(Listener[_FacadeEvent]):
            async def handle(self, event: _FacadeEvent) -> None:
                seen.append(event.tag)

        dispatcher.listen(_FacadeEvent, Cap)
        EventFacade.bind(dispatcher)
        await EventFacade.dispatch(_FacadeEvent(tag="facade-test"))
        assert seen == ["facade-test"]
