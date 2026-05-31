"""Create the ``social_accounts`` table.

Columns: ``id``, ``user_id`` (FK → users, cascade), ``provider``,
``provider_id``, ``tokens`` (encrypted text), and timestamps. A unique
constraint on ``(provider, provider_id)`` enforces one link per remote identity.
"""

from __future__ import annotations

from arvel.database import Blueprint, Schema
from arvel.database.schema import ForeignKeyAction


async def up(schema: Schema) -> None:
    """Apply the migration."""

    def _social_accounts(t: Blueprint) -> None:
        t.id()
        # Generic string FK — matches refresh_tokens; no assumption on user PK shape.
        t.string("user_id", length=36).constrained("users", on_delete=ForeignKeyAction.CASCADE)
        t.string("provider", length=40)
        t.string("provider_id", length=255)
        t.text("tokens").nullable()
        t.timestamps()
        t.unique(["provider", "provider_id"], name="social_accounts_provider_unique")
        t.index(["user_id"], name="social_accounts_user_idx")

    schema.create("social_accounts", _social_accounts)


async def down(schema: Schema) -> None:
    """Roll back the migration."""
    schema.drop_if_exists("social_accounts")
