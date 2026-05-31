"""Create the ``oauth_accounts`` table.

Columns: ``id``, ``user_id`` (FK → users, cascade), ``provider``,
``provider_id``, ``tokens`` (encrypted text), and timestamps. A unique
constraint on ``(provider, provider_id)`` enforces one link per remote identity.
"""

from __future__ import annotations

from arvel.database import Blueprint, Schema
from arvel.database.schema import ForeignKeyAction


async def up(schema: Schema) -> None:
    """Apply the migration."""

    def _oauth_accounts(t: Blueprint) -> None:
        t.id()
        # Generic string FK — matches refresh_tokens; no assumption on user PK shape.
        t.string("user_id", length=36).constrained("users", on_delete=ForeignKeyAction.CASCADE)
        t.string("provider", length=40)
        t.string("provider_id", length=255)
        t.text("tokens").nullable()
        t.timestamps()
        t.unique(["provider", "provider_id"], name="oauth_accounts_provider_unique")
        t.index(["user_id"], name="oauth_accounts_user_idx")

    schema.create("oauth_accounts", _oauth_accounts)


async def down(schema: Schema) -> None:
    """Roll back the migration."""
    schema.drop_if_exists("oauth_accounts")
