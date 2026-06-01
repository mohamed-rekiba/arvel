"""Tests for EventServiceProvider."""

from __future__ import annotations

import pytest
from arvel import Application
from arvel.events.dispatcher import EventDispatcher
from arvel.events.event import Event
from arvel.events.listener import Listener
from arvel.events.providers.event_service_provider import EventServiceProvider


class TestEventServiceProvider:
    def test_register_binds_dispatcher(self) -> None:
        app = Application()
        provider = EventServiceProvider(app)
        provider.register()
        dispatcher = app.container.make(EventDispatcher)
        assert isinstance(dispatcher, EventDispatcher)

    @pytest.mark.asyncio
    async def test_boot_binds_event_facade(self) -> None:
        from arvel.facades.event import Event as EventFacade

        app = Application()
        provider = EventServiceProvider(app)
        provider.register()
        await provider.boot()
        assert EventFacade.dispatcher is not None

    @pytest.mark.asyncio
    async def test_register_wires_dispatcher_to_container_for_listener_di(self) -> None:
        app = Application()

        class Mailer:
            def __init__(self) -> None:
                self.sent: list[str] = []

            def send(self, message: str) -> None:
                self.sent.append(message)

        class UserRegistered(Event):
            email: str

        class WelcomeListener(Listener[UserRegistered]):
            def __init__(self, mailer: Mailer) -> None:
                self.mailer = mailer

            async def handle(self, event: UserRegistered) -> None:
                self.mailer.send(event.email)

        mailer = Mailer()
        app.container.instance(Mailer, mailer)
        provider = EventServiceProvider(app)
        provider.register()

        dispatcher = app.container.make(EventDispatcher)
        dispatcher.listen(UserRegistered, WelcomeListener)
        await dispatcher.dispatch(UserRegistered(email="alice@example.com"))

        assert mailer.sent == ["alice@example.com"]
