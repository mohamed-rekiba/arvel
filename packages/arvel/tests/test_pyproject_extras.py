"""Sanity tests for the WI-018 three-way pyproject extras split.

Covers FR-018-13: `queue` → taskiq core; `queue-redis` → taskiq-redis;
`queue-amqp` → taskiq-aio-pika; `all` includes all three.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, cast

import pytest


@pytest.fixture(scope="module")
def extras() -> dict[str, list[str]]:
    """Parse the framework package's pyproject.toml extras section."""
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data: dict[str, Any] = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return cast("dict[str, list[str]]", data["project"]["optional-dependencies"])


def _has_any(deps: list[str], needle: str) -> bool:
    return any(needle in d for d in deps)


class TestQueueExtrasSplit:
    """FR-018-13: 'queue' is taskiq core only; broker drivers live in their own extras."""

    def test_queue_extra_has_taskiq_core(self, extras: dict[str, list[str]]) -> None:
        assert "queue" in extras
        assert _has_any(extras["queue"], "taskiq")

    def test_queue_extra_does_not_include_taskiq_redis(self, extras: dict[str, list[str]]) -> None:
        """The bare `queue` extra must NOT pull in taskiq-redis."""
        assert not _has_any(extras["queue"], "taskiq-redis")

    def test_queue_extra_does_not_include_taskiq_aio_pika(
        self, extras: dict[str, list[str]]
    ) -> None:
        assert not _has_any(extras["queue"], "taskiq-aio-pika")

    def test_queue_redis_extra_exists(self, extras: dict[str, list[str]]) -> None:
        assert "queue-redis" in extras
        assert _has_any(extras["queue-redis"], "taskiq-redis")

    def test_queue_amqp_extra_exists(self, extras: dict[str, list[str]]) -> None:
        assert "queue-amqp" in extras
        assert _has_any(extras["queue-amqp"], "taskiq-aio-pika")

    def test_all_extra_includes_queue_redis_and_queue_amqp(
        self, extras: dict[str, list[str]]
    ) -> None:
        """The `all` extra must reference the new extras so `pip install arvel[all]` is complete."""
        all_deps = extras["all"]
        # Some projects use `arvel[a,b,c]` form which puts the names inside one string
        joined = ",".join(all_deps)
        assert "queue-redis" in joined
        assert "queue-amqp" in joined
