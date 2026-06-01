"""Tests for first-class delay/priority on Job, JobEnvelope, Bus, and Worker."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import ClassVar

import pytest
from arvel.queue.bus import Bus
from arvel.queue.config import QueueConfig, QueueDriver
from arvel.queue.envelope import JobEnvelope
from arvel.queue.job import Job
from arvel.queue.manager import QueueManager
from pydantic import ValidationError


class _DPJob(Job):
    """Test job for delay/priority assertions."""

    value: int = 0
    seen: ClassVar[list[int]] = []

    async def handle(self) -> None:
        _DPJob.seen.append(self.value)


# ---------------------------------------------------------------------------
# — Job.delay
# ---------------------------------------------------------------------------


class TestJobDelayField:
    """Job.delay accepts int (seconds) or timedelta; default 0."""

    def test_default_delay_is_zero(self) -> None:
        job = _DPJob(value=1)
        assert job.delay == 0

    def test_delay_accepts_int_seconds(self) -> None:
        job = _DPJob(value=1, delay=60)
        assert job.delay == 60

    def test_delay_accepts_timedelta(self) -> None:
        job = _DPJob(value=1, delay=timedelta(minutes=2))
        assert isinstance(job.delay, timedelta)
        assert job.delay == timedelta(minutes=2)

    def test_delay_serialized_as_int_seconds_in_envelope(self) -> None:
        job = _DPJob(value=1, delay=timedelta(seconds=30))
        envelope = job.to_envelope()
        assert envelope.delay == 30

    def test_delay_int_passthrough_in_envelope(self) -> None:
        job = _DPJob(value=1, delay=15)
        envelope = job.to_envelope()
        assert envelope.delay == 15

    def test_delay_excluded_from_envelope_payload(self) -> None:
        """`delay` is envelope metadata, not job state — must NOT appear in payload."""
        job = _DPJob(value=1, delay=30)
        envelope = job.to_envelope()
        assert "delay" not in envelope.payload


# ---------------------------------------------------------------------------
# — Job.priority
# ---------------------------------------------------------------------------


class TestJobPriorityField:
    """Job.priority is int 0..9; default 0."""

    def test_default_priority_is_zero(self) -> None:
        job = _DPJob(value=1)
        assert job.priority == 0

    def test_priority_zero_accepted(self) -> None:
        job = _DPJob(value=1, priority=0)
        assert job.priority == 0

    def test_priority_nine_accepted(self) -> None:
        job = _DPJob(value=1, priority=9)
        assert job.priority == 9

    def test_priority_above_nine_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _DPJob(value=1, priority=10)

    def test_negative_priority_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _DPJob(value=1, priority=-1)

    def test_priority_excluded_from_envelope_payload(self) -> None:
        """`priority` is envelope metadata, not job state — must NOT appear in payload."""
        job = _DPJob(value=1, priority=7)
        envelope = job.to_envelope()
        assert "priority" not in envelope.payload

    def test_priority_serialized_in_envelope(self) -> None:
        job = _DPJob(value=1, priority=7)
        envelope = job.to_envelope()
        assert envelope.priority == 7


# ---------------------------------------------------------------------------
# — JobEnvelope wire format
# ---------------------------------------------------------------------------


class TestJobEnvelopeDelayPriority:
    """JobEnvelope carries delay (int seconds) and priority (int)."""

    def test_default_delay_priority_zero(self) -> None:
        env = JobEnvelope(job_class="x.Y", payload={})
        assert env.delay == 0
        assert env.priority == 0

    def test_round_trip_through_json(self) -> None:
        env = JobEnvelope(job_class="x.Y", payload={"a": 1}, delay=42, priority=7)
        restored = JobEnvelope.from_json(env.to_json())
        assert restored.delay == 42
        assert restored.priority == 7

    def test_delay_in_json_payload(self) -> None:
        env = JobEnvelope(job_class="x.Y", payload={}, delay=5)
        data = json.loads(env.to_json())
        assert data["delay"] == 5

    def test_priority_in_json_payload(self) -> None:
        env = JobEnvelope(job_class="x.Y", payload={}, priority=3)
        data = json.loads(env.to_json())
        assert data["priority"] == 3

    def test_envelope_without_delay_priority_defaults_to_zero(self) -> None:
        """Pre-018 envelopes lacking delay/priority must read back as 0 (no error)."""
        raw = json.dumps({"job_class": "x.Y", "payload": {}})
        env = JobEnvelope.from_json(raw)
        assert env.delay == 0
        assert env.priority == 0


# ---------------------------------------------------------------------------
# — Bus.dispatch kwarg overrides
# ---------------------------------------------------------------------------


class TestBusDispatchOverrides:
    """Bus.dispatch(job, *, delay=None, priority=None) overrides Job fields."""

    def setup_method(self) -> None:
        _DPJob.seen.clear()

    @pytest.mark.asyncio
    async def test_dispatch_delay_override_mutates_job(self) -> None:
        """delay=300 on dispatch overrides Job.delay=10 before pushing."""
        manager = QueueManager(QueueConfig(connection=QueueDriver.SYNC))
        bus = Bus(manager)
        job = _DPJob(value=1, delay=10)
        # sync driver will sleep(delay) before handle — so override to 0 to keep test fast
        await bus.dispatch(job, delay=0)
        assert job.delay == 0

    @pytest.mark.asyncio
    async def test_dispatch_priority_override_mutates_job(self) -> None:
        """priority=9 on dispatch overrides Job.priority=3 before pushing."""
        manager = QueueManager(QueueConfig(connection=QueueDriver.SYNC))
        bus = Bus(manager)
        job = _DPJob(value=2, priority=3)
        await bus.dispatch(job, priority=9)
        assert job.priority == 9

    @pytest.mark.asyncio
    async def test_dispatch_none_kwargs_preserve_job_fields(self) -> None:
        """None means 'use the value on the Job' — fields untouched."""
        manager = QueueManager(QueueConfig(connection=QueueDriver.SYNC))
        bus = Bus(manager)
        job = _DPJob(value=3, priority=5, delay=0)  # delay=0 so sync runs immediately
        await bus.dispatch(job)
        assert job.priority == 5
        assert job.delay == 0
