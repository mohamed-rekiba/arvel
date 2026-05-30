"""Job class allowlist registry (ADR-035) and deserialization helper."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.queue.envelope import JobEnvelope

if TYPE_CHECKING:
    from arvel.queue.job import Job

# Maps "module.ClassName" -> Job subclass. Populated by Job.__init_subclass__.
JobRegistry: dict[str, type[Job]] = {}


def deserialize_job(envelope: JobEnvelope) -> Job:
    """Reconstruct a Job from its envelope.

    Raises KeyError if job_class is not in the allowlist.
    Raises pydantic.ValidationError if payload doesn't match the job's schema.
    """
    cls = JobRegistry.get(envelope.job_class)
    if cls is None:
        raise KeyError(
            f"Unknown job class {envelope.job_class!r}. "
            "Import the job module before the worker starts to register it."
        )
    return cls.model_validate(envelope.payload)


__all__ = ["JobRegistry", "deserialize_job"]
