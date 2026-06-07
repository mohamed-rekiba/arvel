"""Create permission tables.

Creates five tables: ``permissions``, ``roles``, ``model_has_permissions``,
``model_has_roles``, and ``role_has_permissions``.

``permissions`` and ``roles`` enforce ``UNIQUE(name, guard_name)`` and carry
timestamps. The pivot tables use composite primary keys (no surrogate id, no
timestamps) — the DB itself enforces uniqueness and rejects duplicate
assignment.
"""

from __future__ import annotations

from arvel.database import Blueprint, Schema


async def up(schema: Schema) -> None:
    """Apply the migration."""

    def _permissions(t: Blueprint) -> None:
        t.id()
        t.string("name", length=125)
        t.string("guard_name", length=125).default("web")
        t.timestamps()
        t.unique(["name", "guard_name"], name="permissions_name_guard_unique")

    def _roles(t: Blueprint) -> None:
        t.id()
        t.string("name", length=125)
        t.string("guard_name", length=125).default("web")
        t.integer("level").default(0).nullable(value=False)
        t.timestamps()
        t.unique(["name", "guard_name"], name="roles_name_guard_unique")

    def _model_has_permissions(t: Blueprint) -> None:
        # Composite PK across (permission_id, model_type, model_id) — DB-enforced uniqueness.
        t.integer("permission_id").primary()
        t.string("model_type", length=255).primary()
        t.string("model_id", length=36).primary()
        t.string("guard_name", length=125).default("web")
        t.index(
            ["model_id", "model_type", "guard_name"],
            name="model_has_permissions_model_idx",
        )

    def _model_has_roles(t: Blueprint) -> None:
        # Composite PK across (role_id, model_type, model_id) — DB-enforced uniqueness.
        t.integer("role_id").primary()
        t.string("model_type", length=255).primary()
        t.string("model_id", length=36).primary()
        t.string("guard_name", length=125).default("web")
        t.index(
            ["model_id", "model_type", "guard_name"],
            name="model_has_roles_model_idx",
        )

    def _role_has_permissions(t: Blueprint) -> None:
        # Composite PK matches the ORM model declaration in models.py.
        t.integer("permission_id").primary()
        t.integer("role_id").primary()

    schema.create("permissions", _permissions)
    schema.create("roles", _roles)
    schema.create("model_has_permissions", _model_has_permissions)
    schema.create("model_has_roles", _model_has_roles)
    schema.create("role_has_permissions", _role_has_permissions)


async def down(schema: Schema) -> None:
    """Roll back the migration."""
    for table in (
        "role_has_permissions",
        "model_has_roles",
        "model_has_permissions",
        "roles",
        "permissions",
    ):
        schema.drop_if_exists(table)
