"""Enhanced Seeder base for the e-commerce demo.

Provides self.db (upsert + table query + insert), self.hash_password(),
and self.now() on top of the framework's abstract Seeder contract.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from arvel.database import Seeder
from arvel.database.db import DB
from arvel.facades.hash import Hash

uuid7 = uuid.uuid7


class _Json:
    """Sentinel wrapping a JSON-serialized string so upsert can auto-cast it to jsonb."""

    __slots__ = ("value",)

    def __init__(self, value: str) -> None:
        self.value = value

    def __str__(self) -> str:
        return self.value


def _coerce(value: Any) -> Any:
    """Serialize dicts/lists to JSON strings for JSONB columns.

    datetime objects are passed through — asyncpg binds them natively to
    TIMESTAMPTZ. Dict/list values are wrapped in _Json so the caller can
    automatically apply a ::jsonb cast without listing every JSONB column.
    """
    if isinstance(value, (dict, list)):
        return _Json(json.dumps(value, ensure_ascii=False))
    return value


class _TableQuery:
    """Minimal builder for seeder-time row lookups."""

    def __init__(self, table: str) -> None:
        self._table = table
        self._conditions: list[tuple[str, Any]] = []

    def where(self, col: str, value: Any) -> _TableQuery:
        q = _TableQuery(self._table)
        q._conditions = [*self._conditions, (col, value)]
        return q

    async def first(self) -> dict[str, Any] | None:
        if not self._conditions:
            raise ValueError("where() required before first()")
        where_parts = " AND ".join(f'"{col}" = :{col}' for col, _ in self._conditions)
        raw_bindings = {
            col: (v.value if isinstance(v := _coerce(val), _Json) else v)
            for col, val in self._conditions
        }
        table_ref = f'"{self._table}"'
        _sel = "SELECT * FROM"
        rows = await DB.select(
            f"{_sel} {table_ref} WHERE {where_parts} LIMIT 1",
            raw_bindings,
        )
        return rows[0] if rows else None


class _SeederDB:
    """DB helper attached to EcommerceSeeder."""

    def table(self, table_name: str) -> _TableQuery:
        return _TableQuery(table_name)

    @staticmethod
    def _conflict_target(column: str) -> str:
        if column.startswith("("):
            return column
        return f'"{column}"'

    async def upsert(
        self,
        table: str,
        *,
        match_on: list[str],
        data: dict[str, Any],
        cast_map: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        """INSERT ... ON CONFLICT (...) DO UPDATE SET ...

        ``cast_map`` maps column names to PostgreSQL type names for columns
        that require an explicit cast (e.g. custom enum types). asyncpg infers
        plain string params as ``text``, so enum columns need ``::enum_type``.

        When match_on is empty, performs a plain INSERT (useful for fresh test DBs).
        Returns the inserted/updated row dict including id.
        """
        coerced = {k: _coerce(v) for k, v in data.items()}
        # Unwrap _Json sentinels to plain strings for the params dict.
        raw = {k: v.value if isinstance(v, _Json) else v for k, v in coerced.items()}
        cols = list(coerced.keys())

        # Build effective cast map: caller-provided + auto-detected JSON columns.
        json_casts = {k: "jsonb" for k, v in coerced.items() if isinstance(v, _Json)}
        cast: dict[str, str] = {**json_casts, **(cast_map or {})}

        placeholders = ", ".join(f"CAST(:{c} AS {cast[c]})" if c in cast else f":{c}" for c in cols)
        col_names = ", ".join(f'"{c}"' for c in cols)
        table_ref = f'"{table}"'

        _ins = "INSERT INTO"
        _sel = "SELECT * FROM"
        if not match_on:
            sql = f"{_ins} {table_ref} ({col_names}) VALUES ({placeholders}) RETURNING *"
            rows = await DB.select(sql, raw)
            return rows[0] if rows else None

        conflict_cols = ", ".join(self._conflict_target(c) for c in match_on)
        # Never update the primary key — changing a PK that has FK references
        # violates constraints and semantically makes no sense for upsert.
        update_cols = [c for c in cols if c not in match_on and c != "id"]
        if update_cols:
            update_set = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in update_cols)
            _do_update = "DO UPDATE SET"
            on_conflict = f"{_do_update} {update_set}"
        else:
            on_conflict = "DO NOTHING"

        sql = (
            f"{_ins} {table_ref} ({col_names}) VALUES ({placeholders})"
            f" ON CONFLICT ({conflict_cols}) {on_conflict} RETURNING *"
        )
        rows = await DB.select(sql, raw)
        if rows:
            return rows[0]

        # DO NOTHING path — fetch existing row
        where_parts = " AND ".join(f'"{c}" = :{c}' for c in match_on)
        bindings = {c: raw[c] for c in match_on}
        existing = await DB.select(
            f"{_sel} {table_ref} WHERE {where_parts} LIMIT 1",
            bindings,
        )
        return existing[0] if existing else None

    async def statement(self, sql: str, bindings: dict[str, Any] | None = None) -> None:
        """Execute a raw SQL statement with no return value."""
        await DB.statement(sql, bindings)


class EcommerceSeeder(Seeder):
    """Seeder base for the e-commerce demo — extends arvel's Seeder."""

    def __init__(self) -> None:
        self.db = _SeederDB()

    def hash_password(self, password: str) -> str:
        """Hash using the framework's default hasher (argon2id)."""
        return Hash.make(password)

    def now(self) -> datetime:
        # 1-second buffer so seeded timestamps are always past PostgreSQL's NOW()
        # at view-refresh time, even under Docker container clock skew.
        return datetime.now(UTC) - timedelta(seconds=1)

    def uuid(self) -> str:
        """Generate a UUID v7 string for application-managed UUID PKs."""
        return str(uuid7())


__all__ = ["EcommerceSeeder"]
