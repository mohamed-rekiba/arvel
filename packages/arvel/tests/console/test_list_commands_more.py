"""List-style console commands."""

from __future__ import annotations

from typing import TypeVar

import typer
from arvel.broadcasting.config import BroadcastConfig
from arvel.broadcasting.manager import BroadcastManager
from arvel.console.commands.channel_list import ChannelListCommand
from arvel.console.commands.event_list import EventListCommand
from arvel.events.dispatcher import EventDispatcher
from arvel.events.event import Event
from arvel.events.listener import Listener
from typer.testing import CliRunner

_T = TypeVar("_T")


class _Container:
    def __init__(self) -> None:
        self._bindings: dict[type[object], object] = {}

    def instance(self, key: type[_T], value: _T) -> None:
        self._bindings[key] = value

    def make(self, key: type[_T]) -> _T:
        value = self._bindings[key]
        if not isinstance(value, key):
            msg = f"Binding for {key.__name__} has wrong type"
            raise TypeError(msg)
        return value


class _App:
    def __init__(self, container: _Container) -> None:
        self.container = container


class _OrderChannel:
    pass


class _OrderCreated(Event):
    pass


class _SendReceipt(Listener[_OrderCreated]):
    async def handle(self, event: _OrderCreated) -> None:
        return None


def test_channel_list_reports_missing_app() -> None:
    typer_app = typer.Typer()
    ChannelListCommand().register(typer_app)

    result = CliRunner().invoke(typer_app, [])

    assert result.exit_code == 2
    assert "broadcasting subsystem not registered" in result.stderr


def test_channel_list_prints_registered_channels() -> None:
    manager = BroadcastManager(BroadcastConfig())
    manager.register_channel("orders.{id}", _OrderChannel)
    container = _Container()
    container.instance(BroadcastManager, manager)
    command = ChannelListCommand()
    object.__setattr__(command, "app", _App(container))
    typer_app = typer.Typer()
    command.register(typer_app)

    result = CliRunner().invoke(typer_app, [])

    assert result.exit_code == 0
    assert "orders.{id}: _OrderChannel" in result.stdout


def test_event_list_reports_missing_app() -> None:
    typer_app = typer.Typer()
    EventListCommand().register(typer_app)

    result = CliRunner().invoke(typer_app, [])

    assert result.exit_code == 2
    assert "event subsystem not registered" in result.stderr


def test_event_list_prints_registered_listeners() -> None:
    dispatcher = EventDispatcher()
    dispatcher.listen(_OrderCreated, _SendReceipt)
    container = _Container()
    container.instance(EventDispatcher, dispatcher)
    command = EventListCommand()
    object.__setattr__(command, "app", _App(container))
    typer_app = typer.Typer()
    command.register(typer_app)

    result = CliRunner().invoke(typer_app, [])

    assert result.exit_code == 0
    assert "_OrderCreated:" in result.stdout
    assert "_SendReceipt" in result.stdout
