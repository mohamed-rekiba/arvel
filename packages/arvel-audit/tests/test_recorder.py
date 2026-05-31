"""ActivityRecorder fluent API + ActivityQuery, including subject-redaction guard."""

from __future__ import annotations

import pytest
from arvel.database.model import Model
from arvel_audit import ActivityQuery, MissingActivityDescription, activity
from arvel_audit.auditable import Auditable
from sqlalchemy import Integer, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

pytestmark = pytest.mark.asyncio


class Account(Model):
    __tablename__ = "activity_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    name: Mapped[str] = mapped_column(String(100), nullable=False)


class Report(Model, Auditable):
    __tablename__ = "activity_reports"
    __audit_redact__ = {"token"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    token: Mapped[str] = mapped_column(String(100), nullable=False, default="")


async def test_full_chain_records_subject_and_causer(tables: None, session: AsyncSession) -> None:
    user = Account(name="alice")
    report = Report(title="Q1", token="x")
    session.add_all([user, report])
    await session.flush()

    entry = (
        await activity("exports", session=session)
        .log("Exported Q1 report")
        .by(user)
        .on(report)
        .with_properties({"format": "pdf", "rows": 1200})
        .save()
    )

    assert entry.log_name == "exports"
    assert entry.description == "Exported Q1 report"
    assert entry.causer_type == "Account"
    assert entry.causer_id == str(user.id)
    assert entry.subject_type == "Report"
    assert entry.subject_id == str(report.id)
    assert entry.properties == {"format": "pdf", "rows": 1200}


async def test_save_without_log_raises(tables: None, session: AsyncSession) -> None:
    with pytest.raises(MissingActivityDescription):
        await activity("exports", session=session).save()


async def test_no_subject_or_causer_is_allowed(tables: None, session: AsyncSession) -> None:
    entry = await activity(session=session).log("system started").save()
    assert entry.causer_id is None
    assert entry.subject_id is None
    assert entry.log_name == "default"


async def test_subject_redacted_fields_stripped_from_properties(
    tables: None, session: AsyncSession
) -> None:
    report = Report(title="Q1", token="x")
    session.add(report)
    await session.flush()

    entry = (
        await activity("exports", session=session)
        .log("Exported")
        .on(report)
        .with_properties({"token": "leak-me", "format": "pdf"})
        .save()
    )

    assert "token" not in entry.properties
    assert entry.properties == {"format": "pdf"}


async def test_activity_query_by_subject_and_causer(tables: None, session: AsyncSession) -> None:
    user = Account(name="alice")
    report = Report(title="Q1", token="x")
    session.add_all([user, report])
    await session.flush()
    await activity("exports", session=session).log("Exported").by(user).on(report).save()

    by_subject = await ActivityQuery(session).for_subject(report).get()
    assert len(by_subject) == 1
    by_causer = await ActivityQuery(session).by_causer(user).get()
    assert len(by_causer) == 1
