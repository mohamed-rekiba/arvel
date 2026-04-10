"""Tests for audit trail — Story 3."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from arvel.audit import AuditAction, AuditLog
from tests._fixtures.database import SampleUser

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class TestAuditLog:
    @pytest.mark.anyio
    async def test_record_created(self, db_session: AsyncSession) -> None:
        user = SampleUser(name="Alice", password="secret123")
        db_session.add(user)
        await db_session.flush()

        audit = AuditLog(db_session)
        entry = await audit.record(
            action=AuditAction.CREATED,
            model=user,
            actor_id="admin-1",
            new_values={"name": "Alice"},
        )
        assert entry.action == "created"
        assert entry.model_type == "SampleUser"
        assert entry.actor_id == "admin-1"

    @pytest.mark.anyio
    async def test_record_updated_with_old_new(self, db_session: AsyncSession) -> None:
        user = SampleUser(name="Bob", password="pw")
        db_session.add(user)
        await db_session.flush()

        audit = AuditLog(db_session)
        entry = await audit.record(
            action=AuditAction.UPDATED,
            model=user,
            actor_id="admin-1",
            old_values={"name": "Bob"},
            new_values={"name": "Robert"},
        )
        assert entry.old_values == {"name": "Bob"}
        assert entry.new_values == {"name": "Robert"}

    @pytest.mark.anyio
    async def test_for_model_returns_chronological(self, db_session: AsyncSession) -> None:
        user = SampleUser(name="Charlie", password="pw")
        db_session.add(user)
        await db_session.flush()

        audit = AuditLog(db_session)
        await audit.record(action=AuditAction.CREATED, model=user, new_values={"name": "Charlie"})
        await audit.record(
            action=AuditAction.UPDATED,
            model=user,
            old_values={"name": "Charlie"},
            new_values={"name": "Charles"},
        )

        entries = await audit.for_model(SampleUser, user.id)
        assert len(entries) == 2
        assert entries[0].action == "created"
        assert entries[1].action == "updated"


class TestRedaction:
    def test_sensitive_fields_redacted(self) -> None:
        from arvel.audit.service import _redact

        result = _redact({"name": "Diana", "password": "supersecret"}, {"password"})
        assert result["password"] == "[REDACTED]"
        assert result["name"] == "Diana"

    def test_no_redact_fields(self) -> None:
        from arvel.audit.service import _redact

        result = _redact({"name": "Diana"}, set())
        assert result == {"name": "Diana"}
