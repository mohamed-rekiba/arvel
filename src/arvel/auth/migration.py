"""Framework-shipped auth migrations.

Registers the ``users`` and ``auth_refresh_tokens`` tables via
:func:`register_framework_migration` so that ``arvel db publish``
copies them into the project's ``database/migrations/`` directory
when they don't already exist.

The users table includes ``deleted_at`` (SoftDeletes) and
``email_verified_at`` (MustVerifyEmail) because both are framework
features that operate on this table.
"""

from __future__ import annotations

from arvel.data.migrations import register_framework_migration

# ── 001: users ───────────────────────────────────────────────

_USERS_FILENAME = "001_create_users_table.py"

_USERS_CONTENT = '''\
"""Create the users table.

This migration is shipped by the Arvel auth module.  You can add custom
columns by editing this file — the framework will not overwrite it once
published.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.data import Schema

if TYPE_CHECKING:
    from arvel.data import Blueprint


def upgrade() -> None:
    def users(table: Blueprint) -> None:
        table.id()
        table.string("name")
        table.string("email").unique()
        table.string("password")
        table.datetime("email_verified_at").nullable()
        table.soft_deletes()
        table.timestamps()

    Schema.create("users", users)


def downgrade() -> None:
    Schema.drop("users")
'''

register_framework_migration(_USERS_FILENAME, _USERS_CONTENT)


# ── 002: auth_refresh_tokens ────────────────────────────────

_REFRESH_TOKENS_FILENAME = "002_create_auth_refresh_tokens.py"

_REFRESH_TOKENS_CONTENT = '''\
"""Create auth refresh token persistence table.

This migration is shipped by the Arvel auth module.  You can customise
it after publishing — the framework will not overwrite it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.data import ForeignKeyAction, Schema

if TYPE_CHECKING:
    from arvel.data import Blueprint


def upgrade() -> None:
    def auth_refresh_tokens(table: Blueprint) -> None:
        table.id()
        table.foreign_id("user_id").references(
            "users",
            "id",
            on_delete=ForeignKeyAction.CASCADE,
            on_update=ForeignKeyAction.CASCADE,
        ).nullable().index()
        table.string("token_hash")
        table.datetime("issued_at")
        table.datetime("expires_at")
        table.datetime("revoked_at").nullable()

    Schema.create("auth_refresh_tokens", auth_refresh_tokens)


def downgrade() -> None:
    Schema.drop("auth_refresh_tokens")
'''

register_framework_migration(_REFRESH_TOKENS_FILENAME, _REFRESH_TOKENS_CONTENT)
