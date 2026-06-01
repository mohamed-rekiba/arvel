"""Tests for the deserialization allowlist"""

from __future__ import annotations

import pytest
from arvel.queue.envelope import JobEnvelope
from arvel.queue.job import Job
from arvel.queue.registry import JobRegistry, deserialize_job


class AllowedJob(Job):
    x: int

    async def handle(self) -> None:
        pass


class TestJobDeserialization:
    def test_known_class_deserializes(self) -> None:
        env = JobEnvelope(
            job_class=f"{AllowedJob.__module__}.{AllowedJob.__qualname__}",
            payload={"x": 5},
        )
        job = deserialize_job(env)
        assert isinstance(job, AllowedJob)
        assert job.x == 5

    def test_unknown_class_raises(self) -> None:
        env = JobEnvelope(job_class="evil.module.Exploit", payload={})
        with pytest.raises(KeyError):
            deserialize_job(env)

    def test_malformed_payload_raises(self) -> None:
        env = JobEnvelope(
            job_class=f"{AllowedJob.__module__}.{AllowedJob.__qualname__}",
            payload={"x": "not-an-int"},
        )
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            deserialize_job(env)

    def test_registry_does_not_contain_builtin_types(self) -> None:
        for key in JobRegistry:
            assert "builtins" not in key

    def test_registry_only_contains_job_subclasses(self) -> None:
        for cls in JobRegistry.values():
            assert issubclass(cls, Job)
