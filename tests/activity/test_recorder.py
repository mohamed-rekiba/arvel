"""Tests for activity log — Story 4."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from arvel.activity import activity
from arvel.activity.recorder import ActivityQuery
from tests._fixtures.database import SampleUser

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class TestActivityRecorder:
    @pytest.mark.anyio
    async def test_basic_record(self, db_session: AsyncSession) -> None:
        entry = await activity("users", session=db_session).log("logged_in").save()
        assert entry.log_name == "users"
        assert entry.description == "logged_in"

    @pytest.mark.anyio
    async def test_with_causer(self, db_session: AsyncSession) -> None:
        user = SampleUser(name="Alice", password="pw")
        db_session.add(user)
        await db_session.flush()

        entry = await activity("users", session=db_session).log("logged_in").by(user).save()
        assert entry.causer_type == "SampleUser"
        assert entry.causer_id == str(user.id)

    @pytest.mark.anyio
    async def test_with_subject(self, db_session: AsyncSession) -> None:
        user = SampleUser(name="Bob", password="pw")
        db_session.add(user)
        await db_session.flush()

        entry = await activity("orders", session=db_session).log("order_placed").on(user).save()
        assert entry.subject_type == "SampleUser"
        assert entry.subject_id == str(user.id)

    @pytest.mark.anyio
    async def test_with_properties(self, db_session: AsyncSession) -> None:
        entry = await (
            activity("auth", session=db_session)
            .log("password_changed")
            .with_properties({"ip": "10.0.0.1"})
            .save()
        )
        assert entry.properties == {"ip": "10.0.0.1"}


class TestActivityQuery:
    @pytest.mark.anyio
    async def test_for_subject(self, db_session: AsyncSession) -> None:
        user = SampleUser(name="Carol", password="pw")
        db_session.add(user)
        await db_session.flush()

        await activity("users", session=db_session).log("logged_in").on(user).save()
        await activity("users", session=db_session).log("profile_updated").on(user).save()

        query = ActivityQuery(db_session)
        entries = await query.for_subject(user)
        assert len(entries) == 2

    @pytest.mark.anyio
    async def test_by_causer(self, db_session: AsyncSession) -> None:
        admin = SampleUser(name="Admin", password="pw")
        db_session.add(admin)
        await db_session.flush()

        await activity("admin", session=db_session).log("user_banned").by(admin).save()

        query = ActivityQuery(db_session)
        entries = await query.by_causer(admin)
        assert len(entries) == 1
        assert entries[0].description == "user_banned"
