"""Tests for failed job storage — Story 4.

FR-017: Failed job recording in database table.
NFR-007: Failed job payloads redact sensitive fields.
"""

from __future__ import annotations

from arvel.queue.failed_jobs import (
    SENSITIVE_FIELD_PLACEHOLDER,
    FailedJob,
    redact_payload,
)


class TestFailedJobModel:
    """FR-017: FailedJob SA model stores permanently failed jobs."""

    def test_model_has_required_columns(self) -> None:
        columns = {c.name for c in FailedJob.__table__.columns}
        assert "id" in columns
        assert "job_class" in columns
        assert "queue_name" in columns
        assert "payload" in columns
        assert "exception_class" in columns
        assert "exception_message" in columns
        assert "attempts" in columns
        assert "failed_at" in columns

    def test_tablename_is_failed_jobs(self) -> None:
        assert FailedJob.__tablename__ == "failed_jobs"

    def test_job_class_is_indexed(self) -> None:
        col = FailedJob.__table__.columns["job_class"]
        assert col.index is True

    def test_queue_name_is_indexed(self) -> None:
        col = FailedJob.__table__.columns["queue_name"]
        assert col.index is True

    def test_failed_at_is_indexed(self) -> None:
        col = FailedJob.__table__.columns["failed_at"]
        assert col.index is True


class TestPayloadRedaction:
    """NFR-007: Sensitive fields redacted before storage."""

    def test_redact_replaces_sensitive_keys(self) -> None:
        payload = {"user_id": "u1", "password": "secret", "token": "abc123"}
        sensitive = frozenset({"password", "token"})
        result = redact_payload(payload, sensitive)
        assert result["password"] == SENSITIVE_FIELD_PLACEHOLDER
        assert result["token"] == SENSITIVE_FIELD_PLACEHOLDER
        assert result["user_id"] == "u1"

    def test_redact_preserves_non_sensitive_keys(self) -> None:
        payload = {"name": "Alice", "email": "a@b.com"}
        result = redact_payload(payload, frozenset({"password"}))
        assert result == payload

    def test_redact_handles_empty_payload(self) -> None:
        result = redact_payload({}, frozenset({"password"}))
        assert result == {}

    def test_redact_handles_missing_sensitive_keys(self) -> None:
        payload = {"name": "Alice"}
        result = redact_payload(payload, frozenset({"password", "token"}))
        assert result == {"name": "Alice"}

    def test_redact_does_not_mutate_original(self) -> None:
        payload = {"password": "secret"}
        _ = redact_payload(payload, frozenset({"password"}))
        assert payload["password"] == "secret"
