"""JobEnvelope — the JSON wire format for a queued job.

WI-018 added ``delay`` (int seconds) and ``priority`` (int 0..9) per ADR-066.
Pre-018 envelopes lacking these fields read back as ``delay=0, priority=0``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast


@dataclass
class JobEnvelope:
    """Serialized form of a Job, stored in the queue backend."""

    job_class: str
    payload: dict[str, Any]
    attempts: int = 0
    delay: int = 0
    priority: int = 0

    def to_json(self) -> str:
        return json.dumps(
            {
                "job_class": self.job_class,
                "payload": self.payload,
                "attempts": self.attempts,
                "delay": self.delay,
                "priority": self.priority,
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
        return cls(
            job_class=str(data["job_class"]),
            payload=payload,
            attempts=int(data.get("attempts", 0)),
            delay=int(data.get("delay", 0)),
            priority=int(data.get("priority", 0)),
        )


__all__ = ["JobEnvelope"]
