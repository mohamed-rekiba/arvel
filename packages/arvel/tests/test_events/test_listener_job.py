"""Tests for ListenerJob."""

from __future__ import annotations

import pytest
from arvel import Application
from arvel.events.event import Event, EventRegistry
from arvel.events.listener import Listener
from arvel.events.listener_job import ListenerJob
from arvel.events.providers.event_service_provider import EventServiceProvider
from arvel.queue.registry import JobRegistry


class _PayEvent(Event):
    amount: int


class _PayListener(Listener[_PayEvent]):
    results: list[int] = []

    async def handle(self, event: _PayEvent) -> None:
        _PayListener.results.append(event.amount)


class TestListenerJob:
    """/007: ListenerJob serializes and re-runs a listener."""

    def setup_method(self) -> None:
        _PayListener.results.clear()

    def test_listener_job_is_a_job(self) -> None:
        from arvel.queue.job import Job

        assert issubclass(ListenerJob, Job)

    def test_listener_job_auto_registered_in_job_registry(self) -> None:
        key = f"{ListenerJob.__module__}.{ListenerJob.__qualname__}"
        assert key in JobRegistry

    def test_listener_class_key_format(self) -> None:
        ev = _PayEvent(amount=50)
        job = ListenerJob.create(listener_cls=_PayListener, event=ev)
        expected_listener_key = f"{_PayListener.__module__}.{_PayListener.__qualname__}"
        assert job.listener_class_key == expected_listener_key

    def test_event_class_key_format(self) -> None:
        ev = _PayEvent(amount=50)
        job = ListenerJob.create(listener_cls=_PayListener, event=ev)
        expected_event_key = f"{_PayEvent.__module__}.{_PayEvent.__qualname__}"
        assert job.event_class_key == expected_event_key

    def test_event_json_is_serialized(self) -> None:
        ev = _PayEvent(amount=99)
        job = ListenerJob.create(listener_cls=_PayListener, event=ev)
        assert '"amount"' in job.event_json
        assert "99" in job.event_json

    @pytest.mark.asyncio
    async def test_handle_deserializes_and_calls_listener(self) -> None:
        ev = _PayEvent(amount=42)
        job = ListenerJob.create(listener_cls=_PayListener, event=ev)
        await job.handle()
        assert _PayListener.results == [42]

    @pytest.mark.asyncio
    async def test_handle_resolves_listener_through_bound_dispatcher_container(self) -> None:
        class Recorder:
            def __init__(self) -> None:
                self.values: list[int] = []

        class InjectedListener(Listener[_PayEvent]):
            def __init__(self, recorder: Recorder) -> None:
                self.recorder = recorder

            async def handle(self, event: _PayEvent) -> None:
                self.recorder.values.append(event.amount)

        recorder = Recorder()
        app = Application()
        app.container.instance(Recorder, recorder)
        provider = EventServiceProvider(app)
        provider.register()
        await provider.boot()

        job = ListenerJob.create(listener_cls=InjectedListener, event=_PayEvent(amount=7))
        await job.handle()

        assert recorder.values == [7]

    @pytest.mark.asyncio
    async def test_unknown_listener_class_raises_key_error(self) -> None:
        job = ListenerJob(
            listener_class_key="nonexistent.module.Listener",
            event_class_key=f"{_PayEvent.__module__}.{_PayEvent.__qualname__}",
            event_json=_PayEvent(amount=1).model_dump_json(),
        )
        with pytest.raises(KeyError):
            await job.handle()

    def test_event_class_registered_in_event_registry(self) -> None:
        key = f"{_PayEvent.__module__}.{_PayEvent.__qualname__}"
        assert key in EventRegistry
