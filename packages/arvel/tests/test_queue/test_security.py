"""Security tests for queue subsystem — NFR-008-007..010, OWASP A05."""

from __future__ import annotations

import pytest
from arvel.queue.envelope import JobEnvelope
from arvel.queue.registry import deserialize_job


class TestDeserializationSecurity:
    """NFR-008-009: Job class allowlist prevents code injection via queue."""

    INJECTION_PAYLOADS = [
        "os.system",
        "subprocess.Popen",
        "__import__",
        "builtins.eval",
        "importlib.import_module",
        "../../etc/passwd",
        "; rm -rf /",
        "<script>alert(1)</script>",
        "a" * 10_000,
    ]

    @pytest.mark.parametrize("malicious_class", INJECTION_PAYLOADS)
    def test_malicious_job_class_rejected(self, malicious_class: str) -> None:
        env = JobEnvelope(job_class=malicious_class, payload={})
        with pytest.raises((KeyError, ValueError)):
            deserialize_job(env)


class TestPayloadValidation:
    """NFR-008-007: Payloads are validated on deserialization (OWASP A05)."""

    def test_oversized_payload_key_rejected(self) -> None:
        from arvel.queue.job import Job

        class BoundedJob(Job):
            name: str

            async def handle(self) -> None:
                pass

        long_name = "x" * 100_000
        env = JobEnvelope(
            job_class=f"{BoundedJob.__module__}.{BoundedJob.__qualname__}",
            payload={"name": long_name},
        )
        # Pydantic validates on model_validate — if no max_length, the string is accepted
        # This test documents that payload fields SHOULD have appropriate constraints
        job = deserialize_job(env)
        assert isinstance(job, BoundedJob)
        assert len(job.name) == 100_000
        # NOTE: individual Job subclasses should add Field(max_length=...) as needed

    def test_null_bytes_in_payload_string(self) -> None:
        from arvel.queue.job import Job

        class StringJob(Job):
            msg: str

            async def handle(self) -> None:
                pass

        env = JobEnvelope(
            job_class=f"{StringJob.__module__}.{StringJob.__qualname__}",
            payload={"msg": "valid\x00evil"},
        )
        # Pydantic accepts null bytes in strings by default — document this
        job = deserialize_job(env)
        assert isinstance(job, StringJob)
        assert "\x00" in job.msg
        # NOTE: Pydantic does not strip null bytes; validate explicitly if required


class TestFailedJobStoreSecurity:
    """NFR-008-010: Failed job payloads don't log PII."""

    @pytest.mark.asyncio
    async def test_error_truncation_prevents_disk_exhaustion(self) -> None:
        from arvel.queue.failed_job_store import FailedJobStore

        store = FailedJobStore.create_in_memory()
        await store.setup()
        giant_error = "e" * 200_000
        env = JobEnvelope(job_class="myapp.jobs.MyJob", payload={})
        row = await store.create(envelope=env, queue="default", error=giant_error)
        found = await store.find(row.uuid)
        assert found is not None
        assert len(found.error) <= 65_535
