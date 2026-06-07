"""Tests for JobEnvelope wire format"""

from __future__ import annotations

import json

import pytest
from arvel.queue.envelope import JobEnvelope


class TestJobEnvelope:
    def test_to_json_produces_valid_json(self) -> None:
        env = JobEnvelope(job_class="myapp.jobs.Foo", payload={"x": 1})
        s = env.to_json()
        parsed = json.loads(s)
        assert parsed["job_class"] == "myapp.jobs.Foo"
        assert parsed["payload"] == {"x": 1}

    def test_from_json_round_trip(self) -> None:
        env = JobEnvelope(job_class="myapp.jobs.Foo", payload={"x": 1})
        s = env.to_json()
        restored = JobEnvelope.from_json(s)
        assert restored.job_class == "myapp.jobs.Foo"
        assert restored.payload == {"x": 1}

    def test_from_json_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            JobEnvelope.from_json("not-json")

    def test_from_json_missing_fields_raises(self) -> None:
        with pytest.raises((ValueError, KeyError)):
            JobEnvelope.from_json(json.dumps({"job_class": "Foo"}))

    def test_payload_must_be_dict(self) -> None:
        json_with_non_dict_payload = json.dumps({"job_class": "Foo", "payload": "not-a-dict"})
        with pytest.raises((TypeError, ValueError)):
            JobEnvelope.from_json(json_with_non_dict_payload)


class TestJobEnvelopeId:
    """Each envelope carries a unique id so identical jobs don't collapse."""

    def test_two_envelopes_for_same_job_have_distinct_ids(self) -> None:
        a = JobEnvelope(job_class="myapp.jobs.Foo", payload={"x": 1})
        b = JobEnvelope(job_class="myapp.jobs.Foo", payload={"x": 1})
        assert a.id != b.id
        # The Redis driver keys on the JSON; distinct ids keep members distinct.
        assert a.to_json() != b.to_json()

    def test_id_round_trips(self) -> None:
        env = JobEnvelope(job_class="Foo", payload={})
        restored = JobEnvelope.from_json(env.to_json())
        assert restored.id == env.id

    def test_missing_id_gets_generated(self) -> None:
        raw = json.dumps({"job_class": "Foo", "payload": {}})
        env = JobEnvelope.from_json(raw)
        assert env.id


class TestJobEnvelopeAttempts:
    """JobEnvelope carries an attempts counter."""

    def test_default_attempts_is_zero(self) -> None:
        env = JobEnvelope(job_class="myapp.jobs.Foo", payload={"x": 1})
        assert env.attempts == 0

    def test_attempts_serialized_in_json(self) -> None:
        env = JobEnvelope(job_class="myapp.jobs.Foo", payload={"x": 1}, attempts=2)
        parsed = json.loads(env.to_json())
        assert parsed["attempts"] == 2

    def test_attempts_deserialized_from_json(self) -> None:
        raw = json.dumps({"job_class": "Foo", "payload": {}, "attempts": 3})
        env = JobEnvelope.from_json(raw)
        assert env.attempts == 3

    def test_attempts_defaults_to_zero_for_old_envelopes(self) -> None:
        """Backward compat: envelopes without 'attempts' key must deserialize cleanly."""
        raw = json.dumps({"job_class": "Foo", "payload": {}})
        env = JobEnvelope.from_json(raw)
        assert env.attempts == 0

    def test_attempts_round_trip(self) -> None:
        env = JobEnvelope(job_class="Foo", payload={}, attempts=5)
        restored = JobEnvelope.from_json(env.to_json())
        assert restored.attempts == 5
