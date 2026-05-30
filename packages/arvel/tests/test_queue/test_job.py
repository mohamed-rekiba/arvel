"""Tests for Job base class — FR-008-001..003, FR-008-013."""

from __future__ import annotations

import pytest
from arvel.queue.job import Job
from arvel.queue.registry import JobRegistry
from pydantic import ValidationError


class MyJob(Job):
    value: int

    async def handle(self) -> None:
        pass


class UnregisteredJob(Job):
    """Registered by __init_subclass__ — should appear in registry."""

    async def handle(self) -> None:
        pass


class TestJobModel:
    """FR-008-001: Job is a Pydantic BaseModel."""

    def test_job_has_queue_attribute(self) -> None:
        job = MyJob(value=1)
        assert job.queue == "default"

    def test_job_accepts_custom_queue(self) -> None:
        job = MyJob(value=1, queue="high")
        assert job.queue == "high"

    def test_job_has_tries_attribute(self) -> None:
        job = MyJob(value=1)
        assert job.tries >= 1

    def test_job_has_timeout_attribute(self) -> None:
        job = MyJob(value=1)
        assert job.timeout > 0

    def test_job_payload_serialization(self) -> None:
        job = MyJob(value=42)
        data = job.model_dump()
        assert data["value"] == 42

    def test_job_validation_rejects_invalid_payload(self) -> None:
        with pytest.raises(ValidationError):
            MyJob.model_validate({"value": "not-an-int"})


class TestJobSerialization:
    """FR-008-002: Jobs serialize to/from JSON envelope."""

    def test_to_envelope_contains_job_class(self) -> None:
        job = MyJob(value=7)
        envelope = job.to_envelope()
        assert "arvel" in envelope.job_class or "MyJob" in envelope.job_class

    def test_to_envelope_contains_payload(self) -> None:
        job = MyJob(value=7)
        envelope = job.to_envelope()
        assert envelope.payload["value"] == 7

    def test_envelope_round_trip(self) -> None:
        job = MyJob(value=99)
        envelope = job.to_envelope()
        json_str = envelope.to_json()
        restored = envelope.from_json(json_str)
        assert restored.payload["value"] == 99
        assert restored.job_class == envelope.job_class

    def test_to_envelope_preserves_tries(self) -> None:
        """FR-011-002: tries must survive envelope serialization."""
        job = MyJob(value=1, tries=5)
        envelope = job.to_envelope()
        assert envelope.payload["tries"] == 5

    def test_to_envelope_default_tries(self) -> None:
        job = MyJob(value=1)
        envelope = job.to_envelope()
        assert "tries" in envelope.payload


class TestJobRegistry:
    """FR-008-013: Job classes auto-register via __init_subclass__."""

    def test_my_job_in_registry(self) -> None:
        assert any("MyJob" in key for key in JobRegistry)

    def test_unregistered_job_in_registry(self) -> None:
        assert any("UnregisteredJob" in key for key in JobRegistry)

    def test_registry_maps_to_job_subclass(self) -> None:
        for cls in JobRegistry.values():
            assert issubclass(cls, Job)
