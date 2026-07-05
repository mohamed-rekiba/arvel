"""arvel.queue.listener.CallQueuedListener — the worker job that runs a queued event listener.

Covers both carriage forms: a listener registered as a **class** (container-resolved in the
worker) and an already-constructed **instance** (encoded/decoded across the broker), plus the
sync and async ``handle`` return paths.
"""

from __future__ import annotations

from typing import Any

import pytest

from arvel.kernel import has_application, set_application
from arvel.kernel.application import Application
from arvel.queue.listener import CallQueuedListener

_seen: list[Any] = []


class SyncListener:
    def handle(self, value: Any) -> str:
        _seen.append(("sync", value))
        return f"handled:{value}"


class AsyncListener:
    async def handle(self, value: Any) -> str:
        _seen.append(("async", value))
        return f"async:{value}"


class StatefulListener:
    def __init__(self, suffix: str) -> None:
        self.suffix = suffix

    def handle(self, value: Any) -> str:
        return f"{value}{self.suffix}"


@pytest.fixture(autouse=True)
def _clear() -> None:
    _seen.clear()


async def test_class_listener_without_application_instantiates_directly() -> None:
    assert not has_application()
    job = CallQueuedListener.for_listener(SyncListener, ("hi",))
    assert job.is_class is True
    assert await job.handle() == "handled:hi"
    assert _seen == [("sync", "hi")]


async def test_class_listener_awaits_async_handle() -> None:
    job = CallQueuedListener.for_listener(AsyncListener, ("go",))
    assert await job.handle() == "async:go"
    assert _seen == [("async", "go")]


async def test_class_listener_resolves_through_application_when_bound() -> None:
    app = Application()
    set_application(app)
    try:
        assert has_application()
        job = CallQueuedListener.for_listener(SyncListener, ("x",))
        assert await job.handle() == "handled:x"
    finally:
        set_application(None)


async def test_instance_listener_is_encoded_and_decoded() -> None:
    listener = StatefulListener(suffix="!")
    job = CallQueuedListener.for_listener(listener, ("boom",))
    assert job.is_class is False
    assert job.listener_state == {"suffix": "!"}
    assert await job.handle() == "boom!"
