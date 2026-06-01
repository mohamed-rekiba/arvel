"""Tests for ScheduledTask Pydantic model."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest


def test_scheduled_task_is_frozen_pydantic_model() -> None:
    from arvel.scheduling import ScheduledTask

    task = ScheduledTask(
        name="t1",
        description=None,
        expression="0 * * * *",
        timezone="UTC",
        without_overlapping=False,
        on_one_server=False,
        in_maintenance_mode=False,
        output_to=None,
    )
    with pytest.raises((ValueError, TypeError)):
        task.name = "different"  # type: ignore[misc]


def test_scheduled_task_is_due() -> None:
    from arvel.scheduling import ScheduledTask

    task = ScheduledTask(
        name="hourly",
        description=None,
        expression="0 * * * *",
        timezone="UTC",
        without_overlapping=False,
        on_one_server=False,
        in_maintenance_mode=False,
        output_to=None,
    )
    on_the_hour = datetime(2026, 5, 19, 14, 0, 0, tzinfo=UTC)
    off_the_hour = datetime(2026, 5, 19, 14, 30, 0, tzinfo=UTC)

    assert task.is_due(on_the_hour)
    assert not task.is_due(off_the_hour)


def test_scheduled_task_timezone_aware() -> None:
    from arvel.scheduling import ScheduledTask

    task_utc = ScheduledTask(
        name="paris-09",
        description=None,
        expression="0 9 * * *",
        timezone="Europe/Paris",
        without_overlapping=False,
        on_one_server=False,
        in_maintenance_mode=False,
        output_to=None,
    )
    # 07:00 UTC == 09:00 Paris in summer (CEST). Should be due.
    summer_07_utc = datetime(2026, 7, 15, 7, 0, 0, tzinfo=UTC)
    # 08:00 UTC == 10:00 Paris CEST. NOT due.
    summer_08_utc = datetime(2026, 7, 15, 8, 0, 0, tzinfo=UTC)

    assert task_utc.is_due(summer_07_utc)
    assert not task_utc.is_due(summer_08_utc)
