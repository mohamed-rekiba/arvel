"""Coverage — scheduler branches, Collection methods, validation async paths."""

from __future__ import annotations

from datetime import datetime

import pytest

from arvel.queue.scheduler import Schedule, ScheduledEvent
from arvel.support import Collection
from arvel.validation import ValidationException, Validator


# --- scheduler ----------------------------------------------------------------
def test_cron_range_expression() -> None:
    event = ScheduledEvent(lambda: None).cron("1-5 * * * *")
    assert event.is_due(datetime(2026, 1, 1, 0, 3))  # minute 3 in [1,5]
    assert not event.is_due(datetime(2026, 1, 1, 0, 7))


def test_daily_cadence() -> None:
    event = Schedule().call(lambda: None).daily()
    assert event.is_due(datetime(2026, 1, 1, 0, 0))
    assert not event.is_due(datetime(2026, 1, 1, 1, 0))


async def test_async_callback_is_awaited() -> None:
    ran: list[str] = []

    async def cb() -> None:
        ran.append("x")

    await ScheduledEvent(cb).run()
    assert ran == ["x"]


def test_job_and_command_builders_register_events() -> None:
    schedule = Schedule()

    class DummyJob:
        queue = "default"

    schedule.job(DummyJob()).hourly()
    schedule.command("route:list").daily()
    assert len(schedule.events) == 2
    assert all(isinstance(e, ScheduledEvent) for e in schedule.events)


# --- Collection ---------------------------------------------------------------
def test_collection_surface() -> None:
    c: Collection[int] = Collection([1, 2, 3])
    assert c.all() == [1, 2, 3]
    assert c.to_list() == [1, 2, 3]
    assert list(iter(c)) == [1, 2, 3]
    assert len(c) == 3
    assert c == Collection([1, 2, 3])
    assert "Collection" in repr(c)

    seen: list[int] = []
    c.each(lambda x: seen.append(x))
    assert seen == [1, 2, 3]
    assert c.map(lambda x: x * 2).all() == [2, 4, 6]
    assert c.filter(lambda x: x > 1).all() == [2, 3]
    assert c.reduce(lambda acc, x: acc + x, 0) == 6
    assert c.first() == 1


# --- validation async paths ---------------------------------------------------
async def test_passes_async_without_db_skips_db_rules() -> None:
    # no connection + no app -> unique/exists are treated as satisfied; required still applies
    validator = Validator({"email": "a@b.com"}, {"email": "required|unique:users,email"})
    assert await validator.passes_async()


async def test_validate_async_returns_validated() -> None:
    result = await Validator({"name": "Ada"}, {"name": "required"}).validate_async()
    assert result == {"name": "Ada"}


async def test_validate_async_raises_on_failure() -> None:
    with pytest.raises(ValidationException):
        await Validator({}, {"name": "required"}).validate_async()


def test_validator_message_override() -> None:
    validator = Validator({}, {"email": "required"}, messages={"email.required": "Need it."})
    validator.passes()
    assert validator.errors()["email"] == ["Need it."]
