"""Additional Migration coverage — discover_migrations + back-compat paths."""

from __future__ import annotations

from pathlib import Path

import pytest
from arvel.database import Migration, MigrationNotReversibleError, Schema
from arvel.database.migrations import (
    _find_destructive_op,  # pyright: ignore[reportPrivateUsage]  # test verifies the private destructive-op detector
    discover_migrations,
)


def test_discover_returns_sorted(tmp_path: Path) -> None:
    for name in ("2025_a.py", "2024_b.py", "2026_c.py"):
        (tmp_path / name).write_text("# stub")
    paths = list(discover_migrations(tmp_path))
    assert [p.name for p in paths] == ["2024_b.py", "2025_a.py", "2026_c.py"]


def test_discover_returns_empty_iterator_for_missing_dir(tmp_path: Path) -> None:
    missing = tmp_path / "nowhere"
    assert list(discover_migrations(missing)) == []


def test_find_destructive_op_detects_drop_call() -> None:
    src = "def up():\n    Schema.drop('x')\n"
    assert _find_destructive_op(src) == "drop"


def test_find_destructive_op_returns_none_for_safe_up() -> None:
    src = "def up():\n    Schema.create('x', lambda t: None)\n"
    assert _find_destructive_op(src) is None


def test_find_destructive_op_handles_unparseable_source() -> None:
    assert _find_destructive_op("def up(:") is None


def test_migration_with_docstring_only_down_is_treated_empty() -> None:
    async def _up(_self: Migration) -> None:
        Schema.drop("x")

    async def _down(_self: Migration) -> None:
        """still empty"""

    with pytest.raises(MigrationNotReversibleError):
        type("DocOnly", (Migration,), {"up": _up, "down": _down})
