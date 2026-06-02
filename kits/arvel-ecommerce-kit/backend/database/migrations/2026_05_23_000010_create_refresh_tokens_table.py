"""Create the ``refresh_tokens`` table (required by AuthServiceProvider).

Uses String(36) for ``id`` to match the ``RefreshToken`` ORM model, which
stores UUID v7 values as VARCHAR(36) strings rather than native UUID columns.
"""

from __future__ import annotations

from arvel.database import Blueprint, Schema


async def up(schema: Schema) -> None:
    def _table(t: Blueprint) -> None:
        t.string("id", length=36).primary()
        t.string("user_id", length=36)
        t.string("token_hash", length=64).unique()
        t.datetime("expires_at")
        t.datetime("revoked_at").nullable()
        t.timestamps()
        t.index(["user_id"], name="refresh_tokens_user_idx")

    schema.create("refresh_tokens", _table)


async def down(schema: Schema) -> None:
    schema.drop_if_exists("refresh_tokens")
