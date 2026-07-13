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


# --- 5.4: failed() delegates to the wrapped listener, exactly once, on exhaustion ------------


class FailingListener:
    tries = 1
    failed_calls: list[BaseException] = []

    def handle(self, value: str) -> None:
        raise RuntimeError(f"boom:{value}")

    def failed(self, exc: BaseException) -> None:
        FailingListener.failed_calls.append(exc)


class FailingListenerBadHook:
    def handle(self, value: str) -> None:
        raise RuntimeError("boom")

    def failed(self, exc: BaseException) -> None:
        raise RuntimeError("the failure hook itself is broken")


class ListenerWithoutFailedHook:
    def handle(self, value: str) -> None:
        raise RuntimeError("boom")


async def test_failing_listener_gets_failed_exactly_once_on_exhaustion() -> None:
    from arvel.queue import run_job_with_retries

    FailingListener.failed_calls.clear()
    job = CallQueuedListener.for_listener(FailingListener, ("x",))
    job.tries = 1
    await run_job_with_retries(job)
    assert len(FailingListener.failed_calls) == 1
    assert isinstance(FailingListener.failed_calls[0], RuntimeError)


async def test_a_raising_failed_hook_is_swallowed_not_propagated() -> None:
    job = CallQueuedListener.for_listener(FailingListenerBadHook, ("x",))
    await job.failed(RuntimeError("boom"))  # must not raise


async def test_a_wrapped_listener_without_a_failed_hook_is_a_noop() -> None:
    job = CallQueuedListener.for_listener(ListenerWithoutFailedHook, ("x",))
    await job.failed(RuntimeError("boom"))  # no failed() defined -> nothing to call, no crash


async def test_run_job_with_retries_does_not_crash_when_failed_hook_raises() -> None:
    from arvel.queue import run_job_with_retries

    job = CallQueuedListener.for_listener(FailingListenerBadHook, ("x",))
    job.tries = 1
    result = await run_job_with_retries(job)  # must not raise, despite failed() blowing up
    assert result is None
