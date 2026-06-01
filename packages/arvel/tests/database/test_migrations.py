"""Migration reversibility enforcement."""

from __future__ import annotations

import pytest
from arvel.database import Migration, MigrationNotReversibleError, Schema


def test_irreversible_destructive_up_raises_at_class_creation_time() -> None:
    async def _up(_self: Migration) -> None:
        Schema.drop("users")

    async def _down(_self: Migration) -> None:
        pass

    with pytest.raises(MigrationNotReversibleError) as exc:
        type("BadMigration", (Migration,), {"up": _up, "down": _down})

    assert "drop" in str(exc.value).lower()


def test_reversible_migration_is_accepted() -> None:
    def _build(t: object) -> None:
        # Mypy can't see Blueprint methods here because the lambda escapes the
        # generic. We discard the return value to satisfy the
        # Callable[[Blueprint], None] signature.
        from arvel.database.schema import Blueprint

        if isinstance(t, Blueprint):
            t.id()

    class GoodMigration(Migration):
        async def up(self) -> None:
            Schema.drop("users")

        async def down(self) -> None:
            Schema.create("users", _build)

    assert GoodMigration.__name__ == "GoodMigration"


def test_non_destructive_migration_with_empty_down_is_accepted() -> None:
    def _build(t: object) -> None:
        from arvel.database.schema import Blueprint

        if isinstance(t, Blueprint):
            t.id()

    class CreateOnly(Migration):
        async def up(self) -> None:
            Schema.create("widgets", _build)

        async def down(self) -> None:
            pass

    assert CreateOnly.__name__ == "CreateOnly"


def test_drop_column_in_up_requires_down() -> None:
    async def _up(_self: Migration) -> None:
        Schema.table("widgets", lambda t: t.drop_column("legacy"))

    async def _down(_self: Migration) -> None:
        pass

    with pytest.raises(MigrationNotReversibleError):
        type("DroppyColumn", (Migration,), {"up": _up, "down": _down})


def test_notimplemented_down_is_treated_as_empty() -> None:
    async def _up(_self: Migration) -> None:
        Schema.drop("widgets")

    async def _down(_self: Migration) -> None:
        raise NotImplementedError("todo")

    with pytest.raises(MigrationNotReversibleError):
        type("SneakyDown", (Migration,), {"up": _up, "down": _down})
