"""Create foundation tables: users + RBAC (arvel-permission parity).

Mirrors arvel_permission.migrations.create_permission_tables and the
starter's users table so this demo is fully self-contained.
"""

from __future__ import annotations

from arvel.database import Blueprint, Schema


def _users(t: Blueprint) -> None:
    t.id()
    t.string("name", length=120).nullable(value=False)
    t.string("email", length=254).nullable(value=False)
    t.datetime("email_verified_at").nullable()
    t.string("password", length=255).nullable(value=False)
    t.string("locale", length=10).default("en").nullable(value=False)
    t.enum("theme", values=["light", "dark", "system"]).default("system").nullable(value=False)
    t.datetime("suspended_at").nullable()
    t.string("remember_token", length=100).nullable()
    t.timestamps()
    t.soft_deletes()
    t.unique(["email"], name="users_email_unique")
    t.index(["suspended_at"], name="users_suspended_at_idx")


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
    t.id()
    t.integer("permission_id")
    t.string("model_type", length=255)
    t.string("model_id", length=36)
    t.string("guard_name", length=125).default("web")
    t.timestamps()
    t.unique(
        ["permission_id", "model_id", "model_type"],
        name="model_has_permissions_unique",
    )
    t.index(
        ["model_id", "model_type", "guard_name"],
        name="model_has_permissions_model_idx",
    )


def _model_has_roles(t: Blueprint) -> None:
    t.id()
    t.integer("role_id")
    t.string("model_type", length=255)
    t.string("model_id", length=36)
    t.string("guard_name", length=125).default("web")
    t.timestamps()
    t.unique(
        ["role_id", "model_id", "model_type"],
        name="model_has_roles_unique",
    )
    t.index(
        ["model_id", "model_type", "guard_name"],
        name="model_has_roles_model_idx",
    )


def _role_has_permissions(t: Blueprint) -> None:
    t.integer("permission_id")
    t.integer("role_id")
    t.unique(["permission_id", "role_id"], name="role_has_permissions_unique")


async def up(schema: Schema) -> None:
    schema.create("users", _users)
    schema.create("permissions", _permissions)
    schema.create("roles", _roles)
    schema.create("model_has_permissions", _model_has_permissions)
    schema.create("model_has_roles", _model_has_roles)
    schema.create("role_has_permissions", _role_has_permissions)


async def down(schema: Schema) -> None:
    for table in (
        "role_has_permissions",
        "model_has_roles",
        "model_has_permissions",
        "roles",
        "permissions",
        "users",
    ):
        schema.drop_if_exists(table)
    schema.run_sql("DROP TYPE IF EXISTS users_theme")
