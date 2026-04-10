"""Schema facade fluent builder tests."""

from __future__ import annotations

import pytest

from arvel.data.schema import Blueprint, ForeignKeyAction


class TestBlueprintForeignReferences:
    """Foreign-key declaration behavior for migration DSL."""

    def test_foreign_id_can_reference_explicit_table(self) -> None:
        bp = Blueprint()
        bp.foreign_id("parent_user_id").references("users", "id")

        col = bp.columns[0]
        fk = next(iter(col.foreign_keys))
        assert fk.target_fullname == "users.id"

    def test_references_supports_on_delete_and_on_update(self) -> None:
        bp = Blueprint()
        bp.foreign_id("owner_id").references(
            "users",
            "id",
            on_delete=ForeignKeyAction.SET_NULL,
            on_update=ForeignKeyAction.CASCADE,
        )

        col = bp.columns[0]
        fk = next(iter(col.foreign_keys))
        assert fk.target_fullname == "users.id"
        assert fk.ondelete == "SET NULL"
        assert fk.onupdate == "CASCADE"

    def test_on_delete_and_on_update_can_be_chained(self) -> None:
        bp = Blueprint()
        bp.foreign_id("manager_id").references("users").on_delete(
            ForeignKeyAction.RESTRICT
        ).on_update(ForeignKeyAction.CASCADE)

        col = bp.columns[0]
        fk = next(iter(col.foreign_keys))
        assert fk.target_fullname == "users.id"
        assert fk.ondelete == "RESTRICT"
        assert fk.onupdate == "CASCADE"

    def test_on_delete_requires_existing_reference(self) -> None:
        bp = Blueprint()

        with pytest.raises(ValueError, match="foreign key reference"):
            bp.foreign_id("owner_id").on_delete(ForeignKeyAction.CASCADE)
