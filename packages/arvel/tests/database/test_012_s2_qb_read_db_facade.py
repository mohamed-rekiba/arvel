"""WI-arvel-012 Sprint 2 — QB read extensions + DB facade.

Covers FR-012-006 through FR-012-013.

All tests are RED until implementation is complete.
"""

from __future__ import annotations

from typing import Any

import pytest
from arvel.database import Model, foreign_id, id_, integer, relationship, string
from arvel.database.db import DB
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

# ─── Test models ─────────────────────────────────────────────────────────────


class AuthorS2(Model):
    __tablename__ = "authors_s2"
    id: int = id_()
    name: str = string(80)
    score: int = integer(default=0)
    books: list[BookS2] = relationship(
        "BookS2", back_populates="author", init=False, default_factory=list
    )


class BookS2(Model):
    __tablename__ = "books_s2"
    id: int = id_()
    title: str = string(200)
    author_id: int = foreign_id("authors_s2.id")
    author: AuthorS2 | None = relationship("AuthorS2", back_populates="books", init=False)


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


# ─── FR-012-006: Explicit column selection and raw expressions ─────────────────


async def test_select_columns(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    await AuthorS2.create(name="Alice", score=10)
    rows = await AuthorS2.select("id", "name").all()
    assert len(rows) == 1
    # rows contain only requested columns (as dicts or partial objects)
    row = rows[0]
    assert hasattr(row, "name") or (isinstance(row, dict) and "name" in row)


async def test_select_raw(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    for name, score in [("Alice", 10), ("Alice", 20), ("Bob", 5)]:
        await AuthorS2.create(name=name, score=score)
    rows = await AuthorS2.select_raw("name, SUM(score) as total_score").group_by("name").all()
    assert len(rows) >= 1


async def test_where_raw(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    await AuthorS2.create(name="hi", score=50)
    await AuthorS2.create(name="lo", score=5)
    rows = await AuthorS2.where_raw("score > :min", {"min": 10}).all()
    assert len(rows) == 1
    assert rows[0].name == "hi"


async def test_order_by_raw(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    for n in ["C", "A", "B"]:
        await AuthorS2.create(name=n, score=0)
    rows = await AuthorS2.order_by_raw("name ASC").all()
    assert [r.name for r in rows] == ["A", "B", "C"]


async def test_having_raw(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    for name, score in [("X", 1), ("X", 2), ("Y", 100)]:
        await AuthorS2.create(name=name, score=score)
    rows = (
        await AuthorS2.select_raw("name, SUM(score) as s")
        .group_by("name")
        .having_raw("SUM(score) > :n", {"n": 50})
        .all()
    )
    assert len(rows) == 1


# ─── FR-012-007: Joins ────────────────────────────────────────────────────────


async def test_inner_join(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    author = await AuthorS2.create(name="JoinAuthor", score=0)
    await BookS2.create(title="Book1", author_id=author.id)
    rows = await AuthorS2.join(BookS2, BookS2.author_id == AuthorS2.id).all()
    assert len(rows) == 1


async def test_left_join_includes_no_relation(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    await AuthorS2.create(name="NoBook", score=0)
    author_with = await AuthorS2.create(name="HasBook", score=0)
    await BookS2.create(title="OnlyBook", author_id=author_with.id)
    rows = await AuthorS2.left_join(BookS2, BookS2.author_id == AuthorS2.id).all()
    assert len(rows) == 2


# ─── FR-012-008: Additional WHERE variants ────────────────────────────────────


async def test_where_column(engine: AsyncEngine, session: AsyncSession) -> None:
    """where_column compares two columns directly."""
    await _setup(engine)
    # Use score == id as a proxy for "two equal columns"
    a = await AuthorS2.create(name="same", score=0)
    # Force score to match id
    await AuthorS2.where(AuthorS2.id == a.id).update({"score": a.id})
    rows = await AuthorS2.where_column("id", "score").all()
    assert len(rows) >= 1


async def test_where_exists(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    author = await AuthorS2.create(name="WithBook", score=0)
    await AuthorS2.create(name="NoBook", score=0)
    await BookS2.create(title="SomeBook", author_id=author.id)

    rows = (
        await AuthorS2.query()
        .where_exists(lambda q: q.select("1").where(BookS2.author_id == AuthorS2.id))
        .all()
    )
    assert len(rows) == 1
    assert rows[0].name == "WithBook"


async def test_when_applies_clause_when_true(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    await AuthorS2.create(name="Alice", score=10)
    await AuthorS2.create(name="Bob", score=5)
    is_admin = True
    rows = (
        await AuthorS2.query()
        .when(
            is_admin,
            lambda q: q.where(AuthorS2.score >= 10),
        )
        .all()
    )
    assert all(r.score >= 10 for r in rows)


async def test_when_skips_clause_when_false(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    await AuthorS2.create(name="Alice", score=10)
    await AuthorS2.create(name="Bob", score=5)
    rows = (
        await AuthorS2.query()
        .when(
            False,
            lambda q: q.where(AuthorS2.score >= 10),
        )
        .all()
    )
    assert len(rows) == 2


async def test_where_any(engine: AsyncEngine, session: AsyncSession) -> None:
    """where_any applies OR across multiple columns."""
    await _setup(engine)
    await AuthorS2.create(name="alice", score=0)
    await AuthorS2.create(name="other", score=0)
    rows = await AuthorS2.where_any(["name"], "=", "alice").all()
    assert len(rows) == 1


# ─── FR-012-009: Unions ───────────────────────────────────────────────────────


async def test_union(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    await AuthorS2.create(name="active", score=10)
    await AuthorS2.create(name="admin", score=5)
    q1 = AuthorS2.where(AuthorS2.score >= 10)
    q2 = AuthorS2.where(AuthorS2.name == "admin")
    rows = await q1.union(q2).all()
    assert len(rows) == 2


async def test_union_all_includes_duplicates(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    await AuthorS2.create(name="both", score=10)
    q1 = AuthorS2.where(AuthorS2.score >= 5)
    q2 = AuthorS2.where(AuthorS2.name == "both")
    rows = await q1.union_all(q2).all()
    assert len(rows) == 2  # duplicated because union_all


# ─── FR-012-010: Pagination additions ────────────────────────────────────────


async def test_simple_paginate_no_count_query(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    for i in range(10):
        await AuthorS2.create(name=f"a{i}", score=i)
    page = await AuthorS2.order_by(AuthorS2.id).simple_paginate(per_page=4, page=2)
    assert len(page.items) == 4
    # simple paginate does not have a total field
    assert not hasattr(page, "total") or page.total is None


async def test_cursor_paginate_returns_cursors(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    for i in range(10):
        await AuthorS2.create(name=f"c{i}", score=i)
    page = await AuthorS2.order_by(AuthorS2.id).cursor_paginate(per_page=3)
    assert len(page.items) == 3
    assert page.next_cursor is not None


async def test_cursor_paginate_second_page(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    for i in range(8):
        await AuthorS2.create(name=f"cp{i}", score=i)
    first = await AuthorS2.order_by(AuthorS2.id).cursor_paginate(per_page=3)
    second = await AuthorS2.order_by(AuthorS2.id).cursor_paginate(
        per_page=3, cursor=first.next_cursor
    )
    assert len(second.items) == 3
    assert second.items[0].name != first.items[0].name


async def test_cursor_paginate_malformed_cursor_raises(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    """A garbage cursor must raise InvalidCursorError, not silently return page 1."""
    from arvel.database.exceptions import InvalidCursorError

    await _setup(engine)
    for i in range(5):
        await AuthorS2.create(name=f"mc{i}", score=i)

    with pytest.raises(InvalidCursorError):
        await AuthorS2.order_by(AuthorS2.id).cursor_paginate(per_page=2, cursor="!!not-base64!!")


async def test_keyset_paginate_malformed_cursor_raises(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    """Keyset pagination must also reject a malformed cursor loudly."""
    from arvel.database.exceptions import InvalidCursorError

    await _setup(engine)
    for i in range(5):
        await AuthorS2.create(name=f"kc{i}", score=i)

    with pytest.raises(InvalidCursorError):
        await AuthorS2.query().cursor_paginate(
            per_page=2, cursor="@@bad@@", keyset=["score DESC", "id ASC"]
        )


async def test_keyset_paginate_desc_walks_forward_without_overlap(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    """A DESC keyset walk must move toward smaller values, not loop on the head.

    Regression: _apply_keyset_where inverted the comparison, so the second page
    returned the first page's rows again.
    """
    await _setup(engine)
    # Distinct scores so the leading keyset column alone orders every row.
    for i in range(9):
        await AuthorS2.create(name=f"k{i}", score=i)

    keyset = ["score DESC", "id ASC"]
    seen: list[int] = []
    cursor: str | None = None
    for _ in range(5):  # 9 rows / 2 per page → at most 5 pages
        page = await AuthorS2.query().cursor_paginate(per_page=2, cursor=cursor, keyset=keyset)
        seen.extend(a.score for a in page.items)
        if page.next_cursor is None:
            break
        cursor = page.next_cursor

    assert seen == sorted(range(9), reverse=True), seen
    assert len(seen) == len(set(seen)), "pages overlapped"


async def test_keyset_paginate_handles_tied_leading_column(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    """When the leading column ties, the secondary column must break it cleanly."""
    await _setup(engine)
    # All scores equal → ordering falls entirely to the id ASC tiebreaker.
    for i in range(6):
        await AuthorS2.create(name=f"t{i}", score=100)

    keyset = ["score DESC", "id ASC"]
    seen_ids: list[int] = []
    cursor: str | None = None
    for _ in range(4):
        page = await AuthorS2.query().cursor_paginate(per_page=2, cursor=cursor, keyset=keyset)
        seen_ids.extend(a.id for a in page.items)
        if page.next_cursor is None:
            break
        cursor = page.next_cursor

    assert seen_ids == sorted(seen_ids), seen_ids
    assert len(seen_ids) == 6
    assert len(seen_ids) == len(set(seen_ids)), "pages overlapped on tie"


# ─── FR-012-011: Query extras ────────────────────────────────────────────────


async def test_sole_returns_single_result(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    await AuthorS2.create(name="unique_sole", score=0)
    row = await AuthorS2.where(AuthorS2.name == "unique_sole").sole()
    assert row.name == "unique_sole"


async def test_sole_raises_on_empty(engine: AsyncEngine, session: AsyncSession) -> None:
    from arvel.database.exceptions import ModelNotFoundError

    await _setup(engine)
    with pytest.raises(ModelNotFoundError):
        await AuthorS2.where(AuthorS2.name == "no_such").sole()


async def test_sole_raises_on_multiple(engine: AsyncEngine, session: AsyncSession) -> None:
    from arvel.database.exceptions import MultipleResultsError

    await _setup(engine)
    await AuthorS2.create(name="dup", score=1)
    await AuthorS2.create(name="dup", score=2)
    with pytest.raises(MultipleResultsError):
        await AuthorS2.where(AuthorS2.name == "dup").sole()


async def test_first_or_returns_fallback(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    fallback = AuthorS2(name="fallback", score=0)
    result = await AuthorS2.where(AuthorS2.name == "missing").first_or(lambda: fallback)
    assert result.name == "fallback"


async def test_lock_for_update(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    await AuthorS2.create(name="lock_me", score=0)
    row = await AuthorS2.where(AuthorS2.name == "lock_me").lock_for_update().first()
    assert row is not None


# ─── FR-012-012: DB.table() TableQueryBuilder ─────────────────────────────────


async def test_db_table_returns_table_query_builder(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    from arvel.database.db import TableQueryBuilder

    await _setup(engine)
    qb = DB.table("authors_s2")
    assert isinstance(qb, TableQueryBuilder)


async def test_db_table_get_returns_dicts(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    await AuthorS2.create(name="DictRow", score=99)
    rows = await DB.table("authors_s2").where("name", "DictRow").get()
    assert isinstance(rows, list)
    assert len(rows) == 1
    assert isinstance(rows[0], dict)
    assert rows[0]["name"] == "DictRow"


async def test_db_table_write_operations(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    await DB.table("authors_s2").insert([{"name": "table_insert", "score": 5}])
    rows = await DB.table("authors_s2").where("name", "table_insert").get()
    assert len(rows) == 1

    n = await DB.table("authors_s2").where("name", "table_insert").update({"score": 50})
    assert n == 1

    rows = await DB.table("authors_s2").where("name", "table_insert").get()
    assert rows[0]["score"] == 50


async def test_db_table_limit_order_and_delete(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    await DB.table("authors_s2").insert(
        [
            {"name": "delete_a", "score": 2},
            {"name": "delete_b", "score": 1},
        ]
    )

    rows = await DB.table("authors_s2").order_by("score").limit(1).get()
    assert rows[0]["name"] == "delete_b"

    deleted = await DB.table("authors_s2").where("name", "delete_b").delete()
    assert deleted == 1
    remaining = await DB.table("authors_s2").where("name", "delete_b").get()
    assert remaining == []


async def test_db_table_insert_empty_rows_noops(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    await DB.table("authors_s2").insert([])
    assert await DB.scalar("SELECT COUNT(*) FROM authors_s2") == 0


# ─── FR-012-013: DB facade raw SQL methods ────────────────────────────────────


async def test_db_select_returns_dicts(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    await AuthorS2.create(name="raw_select", score=42)
    rows = await DB.select(
        "SELECT name, score FROM authors_s2 WHERE name = :n", {"n": "raw_select"}
    )
    assert isinstance(rows, list)
    assert len(rows) == 1
    assert rows[0]["name"] == "raw_select"
    assert rows[0]["score"] == 42


async def test_db_scalar_returns_single_value(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    await AuthorS2.create(name="sc1", score=0)
    await AuthorS2.create(name="sc2", score=0)
    count = await DB.scalar("SELECT COUNT(*) FROM authors_s2")
    assert count == 2


async def test_db_statement_executes_ddl_style(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    await DB.statement("DELETE FROM authors_s2 WHERE score = 0")
    count = await DB.scalar("SELECT COUNT(*) FROM authors_s2")
    assert count == 0


async def test_db_listen_receives_query_events(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    events: list[str] = []

    def handler(sql: str, bindings: dict[str, Any], duration_ms: float) -> None:
        events.append(sql)

    DB.listen(handler)
    try:
        await DB.select("SELECT 1")
        assert len(events) >= 1
    finally:
        DB.unlisten(handler)


async def test_db_listen_is_idempotent_and_fault_tolerant(
    engine: AsyncEngine,
    session: AsyncSession,
) -> None:
    await _setup(engine)
    events: list[str] = []

    def handler(sql: str, bindings: dict[str, Any], duration_ms: float) -> None:
        events.append(sql)

    def failing_handler(sql: str, bindings: dict[str, Any], duration_ms: float) -> None:
        raise RuntimeError("listener failure")

    DB.listen(handler)
    DB.listen(handler)
    DB.listen(failing_handler)
    try:
        assert await DB.select("SELECT 1 as n") == [{"n": 1}]
        assert len(events) == 1
        DB.unlisten(object())
    finally:
        DB.unlisten(handler)
        DB.unlisten(failing_handler)


async def test_db_connection_routes_to_named_maker(
    engine: AsyncEngine, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    """DB.connection('alt') returns a proxy using the named session maker."""
    DB.configure_named("alt", session_maker)
    proxy = DB.connection("alt")
    # Can execute a query via the proxy
    rows = await proxy.select("SELECT 1 as n")
    assert rows[0]["n"] == 1


async def test_db_raw_sql_uses_configured_session_maker_without_active_session(
    engine: AsyncEngine,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    await _setup(engine)
    previous = type.__getattribute__(DB, "_session_maker")
    try:
        DB.configure(session_maker)
        async with engine.begin() as conn:
            await conn.execute(
                text("INSERT INTO authors_s2 (name, score) VALUES (:name, :score)"),
                {"name": "raw-maker", "score": 7},
            )
        await DB.statement("SELECT 1")
        rows = await DB.select("SELECT name FROM authors_s2 WHERE score = :score", {"score": 7})
        assert rows == [{"name": "raw-maker"}]
        assert await DB.scalar("SELECT COUNT(*) FROM authors_s2") == 1
    finally:
        type.__setattr__(DB, "_session_maker", previous)


async def test_db_connection_proxy_scalar_statement_and_table_error(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    previous = type.__getattribute__(DB, "_session_maker")
    try:
        DB.configure(session_maker)
        proxy = DB.connection()
        assert await proxy.scalar("SELECT 1") == 1
        await proxy.statement("SELECT 1")
        with pytest.raises(RuntimeError, match="active DB session"):
            await proxy.table("authors_s2").get()
    finally:
        type.__setattr__(DB, "_session_maker", previous)


async def test_db_table_requires_active_session_without_connection_maker() -> None:
    with pytest.raises(RuntimeError, match="No active session"):
        await DB.table("authors_s2").get()


async def test_db_unconfigured_errors_without_active_session() -> None:
    previous = type.__getattribute__(DB, "_session_maker")
    previous_named = dict(type.__getattribute__(DB, "_named_makers"))
    type.__setattr__(DB, "_session_maker", None)
    type.__setattr__(DB, "_named_makers", {})
    try:
        with pytest.raises(RuntimeError, match="DB not configured"):
            DB.connection()
        with pytest.raises(RuntimeError, match="No named connection"):
            DB.connection("missing")
        with pytest.raises(RuntimeError, match="DB.select"):
            await DB.select("SELECT 1")
        with pytest.raises(RuntimeError, match="DB.scalar"):
            await DB.scalar("SELECT 1")
        with pytest.raises(RuntimeError, match="DB.statement"):
            await DB.statement("SELECT 1")
        with pytest.raises(RuntimeError, match="DB.transaction"):
            async with DB.transaction():
                pass
    finally:
        type.__setattr__(DB, "_session_maker", previous)
        type.__setattr__(DB, "_named_makers", previous_named)
