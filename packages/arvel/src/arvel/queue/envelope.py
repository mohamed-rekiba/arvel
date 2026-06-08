"""JobEnvelope — the JSON wire format for a queued job.

Envelopes carry ``delay`` (int seconds) and ``priority`` (int 0..9), plus a
``chain`` tail (list of successor descriptors). Successors are dispatched one
at a time by the worker as the predecessor completes successfully — a single
failed link ends the chain.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, TypeGuard, cast


def _is_list_of_any(value: object) -> TypeGuard[list[Any]]:
    return isinstance(value, list)


@dataclass
class ChainStep:
    """One successor in a chained dispatch.

    The successor's routing data (``queue``, ``delay``, ``priority``) is captured
    at chain time so the worker doesn't need to re-instantiate the job to dispatch
    it; only the head job is materialised at queue time.
    """

    job_class: str
    payload: dict[str, Any]
    queue: str = "default"
    delay: int = 0
    priority: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_class": self.job_class,
            "payload": self.payload,
            "queue": self.queue,
            "delay": self.delay,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChainStep:
        raw_payload = data.get("payload")
        if not isinstance(raw_payload, dict):
            raise TypeError("ChainStep.payload must be a JSON object")
        payload = cast("dict[str, Any]", raw_payload)
        return cls(
            job_class=str(data["job_class"]),
            payload=payload,
            queue=str(data.get("queue", "default")),
            delay=int(data.get("delay", 0)),
            priority=int(data.get("priority", 0)),
        )


@dataclass
class JobEnvelope:
    """Serialized form of a Job, stored in the queue backend."""

    job_class: str
    payload: dict[str, Any]
    # Per-dispatch identity. The Redis driver uses the envelope JSON as a ZSET
    # member, so without a unique id two identical jobs would collapse into one
    # and one would be silently dropped. Also gives every job a stable handle.
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    attempts: int = 0
    delay: int = 0
    priority: int = 0
    chain: list[ChainStep] = field(default_factory=list["ChainStep"])
    # Transient reservation handle set by a driver on pop (e.g. the database
    # driver's row id). Never serialized — it identifies the in-flight row so the
    # worker can delete it after processing. None for freshly built envelopes.
    receipt: int | None = field(default=None, compare=False, repr=False)

    def to_json(self) -> str:
        return json.dumps(
            {
                "id": self.id,
                "job_class": self.job_class,
                "payload": self.payload,
                "attempts": self.attempts,
                "delay": self.delay,
                "priority": self.priority,
                "chain": [step.to_dict() for step in self.chain],
            }
        )

    @classmethod
    def from_json(cls, raw: str) -> JobEnvelope:
        try:
            data: dict[str, Any] = json.loads(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"Invalid JobEnvelope JSON: {exc}") from exc
        if "job_class" not in data or "payload" not in data:
            raise ValueError(f"JobEnvelope missing required fields in: {data!r}")
        raw_payload = data["payload"]
        if not isinstance(raw_payload, dict):
            raise TypeError("JobEnvelope.payload must be a JSON object")
        payload = cast("dict[str, Any]", raw_payload)
        raw_chain = data.get("chain", [])
        chain: list[ChainStep] = []
        if _is_list_of_any(raw_chain):
            chain = [
                ChainStep.from_dict(cast("dict[str, Any]", step))
                for step in raw_chain
                if isinstance(step, dict)
            ]
        raw_id = data.get("id")
        return cls(
            job_class=str(data["job_class"]),
            payload=payload,
            id=str(raw_id) if raw_id is not None else uuid.uuid4().hex,
            attempts=int(data.get("attempts", 0)),
            delay=int(data.get("delay", 0)),
            priority=int(data.get("priority", 0)),
            chain=chain,
        )


__all__ = ["ChainStep", "JobEnvelope"]
