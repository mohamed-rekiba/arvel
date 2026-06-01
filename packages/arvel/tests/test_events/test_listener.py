"""Tests for Listener[E] generic abstract class."""

from __future__ import annotations

import pytest
from arvel.events.event import Event
from arvel.events.listener import Listener
from arvel.events.should_queue import ShouldQueue


class _Ev(Event):
    pass


class TestListener:
    """Listener[E] is generic with abstract handle()."""

    def test_listener_is_generic(self) -> None:
        from typing import get_args

        listener_type = Listener[_Ev]
        assert get_args(listener_type)

    def test_concrete_listener_must_implement_handle(self) -> None:
        cls: type = Listener
        with pytest.raises(TypeError):
            cls()

    def test_should_queue_is_a_marker_mixin(self) -> None:
        from arvel.events.event import Event

        class MyEvent(Event):
            x: int

        class MyListener(Listener[MyEvent], ShouldQueue):
            async def handle(self, event: MyEvent) -> None:
                pass

        assert issubclass(MyListener, ShouldQueue)
        assert issubclass(MyListener, Listener)
