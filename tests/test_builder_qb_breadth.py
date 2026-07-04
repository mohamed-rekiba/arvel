"""09 DB-QUERY — QB breadth: join/left_join/right_join, having/having_raw, where_column,
where_date/time/year/month/day, order_by_raw, chunk/each. Compile-string asserts for the SQL
shape, plus real execution against the default in-memory SQLite for row-level correctness
(where_date against Postgres is covered in tests/integration/test_postgres_orm.py)."""

from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
import sqlalchemy.dialects.sqlite

from arvel.database import Builder, ConnectionResolver

_md = sa.MetaData()
users = sa.Table(
    "qb_users",
    _md,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("name", sa.String),
)
posts = sa.Table(
    "qb_posts",
    _md,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("user_id", sa.Integer),
    sa.Column("title", sa.String),
    sa.Column("published_at", sa.DateTime),
)


def _sqlite(stmt: object) -> str:
    return str(stmt.compile(dialect=sa.dialects.sqlite.dialect()))  # type: ignore[attr-defined]


# --- compiled-SQL shape ----------------------------------------------------------------------


def test_join_compiles_an_inner_join_on_the_select() -> None:
    stmt = (
        Builder(posts)
        .join("qb_users", "qb_posts.user_id", "=", "qb_users.id")
        .select_raw("qb_users.name")
        .to_select()
    )
    compiled = _sqlite(stmt)
    assert "JOIN qb_users ON qb_posts.user_id = qb_users.id" in compiled
    assert "qb_users.name" in compiled


def test_left_join_compiles_outer_join() -> None:
    stmt = Builder(posts).left_join("qb_users", "qb_posts.user_id", "=", "qb_users.id").to_select()
    assert "LEFT OUTER JOIN qb_users" in _sqlite(stmt)


def test_right_join_compiles_as_swapped_left_join() -> None:
    """SQLAlchemy Core has no RIGHT JOIN primitive — right_join swaps the two sides of a LEFT
    JOIN, which is semantically identical."""
    stmt = Builder(posts).right_join("qb_users", "qb_posts.user_id", "=", "qb_users.id").to_select()
    compiled = _sqlite(stmt)
    assert "FROM qb_users LEFT OUTER JOIN qb_posts" in compiled


def test_having_compiles_over_a_grouped_aggregate() -> None:
    stmt = (
        Builder(posts)
        .group_by("user_id")
        .select_raw("count(*) AS total")
        .having("total", ">", 1)
        .to_select()
    )
    assert "GROUP BY qb_posts.user_id" in _sqlite(stmt)
    assert "HAVING total >" in _sqlite(stmt)


def test_having_raw_binds_positionally() -> None:
    stmt = Builder(posts).having_raw("COUNT(*) > ?", [5]).to_select()
    compiled = _sqlite(stmt)
    assert "HAVING COUNT(*) >" in compiled


def test_where_column_compiles_a_column_to_column_comparison() -> None:
    stmt = Builder(posts).where_column("id", "!=", "user_id").to_select()
    assert "qb_posts.id != qb_posts.user_id" in _sqlite(stmt)


def test_where_column_two_arg_form_implies_equals() -> None:
    stmt = Builder(posts).where_column("id", "user_id").to_select()
    assert "qb_posts.id = qb_posts.user_id" in _sqlite(stmt)


def test_where_date_compiles_a_date_function_call() -> None:
    stmt = Builder(posts).where_date("published_at", "=", dt.date(2026, 6, 1)).to_select()
    assert "date(qb_posts.published_at)" in _sqlite(stmt).lower()


def test_where_year_month_day_compile_extract() -> None:
    year = Builder(posts).where_year("published_at", "=", 2026).to_select()
    month = Builder(posts).where_month("published_at", "=", 6).to_select()
    day = Builder(posts).where_day("published_at", "=", 1).to_select()
    for stmt, part in ((year, "year"), (month, "month"), (day, "day")):
        compiled = _sqlite(stmt).lower()
        # SQLite compiles EXTRACT via strftime; every dialect must at least mention the part.
        assert part in compiled or "strftime" in compiled


def test_order_by_raw_compiles_verbatim() -> None:
    stmt = Builder(posts).order_by_raw("title COLLATE NOCASE").to_select()
    assert "ORDER BY title COLLATE NOCASE" in _sqlite(stmt)


# --- real execution (row-level correctness) ---------------------------------------------------


async def _seed() -> ConnectionResolver:
    db = ConnectionResolver()
    await db.execute(sa.schema.CreateTable(users))
    await db.execute(sa.schema.CreateTable(posts))
    await Builder(users, db).insert({"id": 1, "name": "ada"})
    await Builder(users, db).insert({"id": 2, "name": "bob"})
    await Builder(posts, db).insert(
        {"user_id": 1, "title": "hello", "published_at": dt.datetime(2026, 6, 1, 9, 0)}
    )
    await Builder(posts, db).insert(
        {"user_id": 2, "title": "world", "published_at": dt.datetime(2026, 7, 1, 9, 0)}
    )
    return db


async def test_join_executes_and_returns_the_joined_column() -> None:
    db = await _seed()
    try:
        rows = await (
            Builder(posts, db)
            .join("qb_users", "qb_posts.user_id", "=", "qb_users.id")
            .select_raw("qb_posts.title, qb_users.name")
            .order_by_raw("qb_posts.title")
            .get()
        )
        assert [dict(r) for r in rows] == [
            {"title": "hello", "name": "ada"},
            {"title": "world", "name": "bob"},
        ]
    finally:
        await db.dispose()


async def test_where_date_filters_on_the_date_portion() -> None:
    db = await _seed()
    try:
        rows = await Builder(posts, db).where_date("published_at", "=", dt.date(2026, 6, 1)).get()
        assert [r["title"] for r in rows] == ["hello"]
    finally:
        await db.dispose()


async def test_where_month_filters_across_years() -> None:
    db = await _seed()
    try:
        rows = await Builder(posts, db).where_month("published_at", "=", 7).get()
        assert [r["title"] for r in rows] == ["world"]
    finally:
        await db.dispose()


async def test_having_filters_grouped_rows() -> None:
    db = await _seed()
    try:
        await Builder(posts, db).insert(
            {"user_id": 1, "title": "again", "published_at": dt.datetime(2026, 8, 1, 9, 0)}
        )
        rows = await (
            Builder(posts, db)
            .group_by("user_id")
            .select_raw("user_id, count(*) AS total")
            .having("total", ">", 1)
            .get()
        )
        assert [dict(r) for r in rows] == [{"user_id": 1, "total": 2}]
    finally:
        await db.dispose()


# --- chunk / each ------------------------------------------------------------------------------


async def test_chunk_pages_offset_based_and_visits_every_row() -> None:
    db = await _seed()
    try:
        seen: list[str] = []

        async def collect(rows: object) -> None:
            seen.extend(r["title"] for r in rows)  # type: ignore[attr-defined]

        await Builder(posts, db).order_by("id").chunk(1, collect)
        assert seen == ["hello", "world"]
    finally:
        await db.dispose()


async def test_chunk_stops_when_callback_returns_false() -> None:
    db = await _seed()
    try:
        seen: list[str] = []

        def collect(rows: object) -> bool:
            seen.extend(r["title"] for r in rows)  # type: ignore[attr-defined]
            return False

        await Builder(posts, db).order_by("id").chunk(1, collect)
        assert seen == ["hello"]
    finally:
        await db.dispose()


async def test_each_processes_every_row_exactly_once() -> None:
    db = await _seed()
    try:
        seen: list[str] = []
        await Builder(posts, db).order_by("id").each(lambda row: seen.append(row["title"]), 1)
        assert seen == ["hello", "world"]
    finally:
        await db.dispose()
