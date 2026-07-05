"""09 DB-QUERY — cursor (keyset) pagination: opaque cursor encode/decode + Builder.cursor_paginate
walking pages with a stable, gap/dup-free ordering (incl. ties, via the pk tiebreaker)."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database import Builder, ConnectionResolver
from arvel.pagination import CursorPaginator, decode_cursor, encode_cursor

_md = sa.MetaData()
items = sa.Table(
    "cp_items",
    _md,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("group", sa.String),
    sa.Column("value", sa.Integer),
)


def test_encode_decode_cursor_round_trips() -> None:
    cursor = encode_cursor({"id": 7, "group": "eu"})
    position, backward = decode_cursor(cursor)
    assert position == {"id": 7, "group": "eu"}
    assert backward is False


def test_encode_decode_cursor_tracks_direction() -> None:
    cursor = encode_cursor({"id": 7}, backward=True)
    _, backward = decode_cursor(cursor)
    assert backward is True


async def _seed(rows: int = 25) -> ConnectionResolver:
    db = ConnectionResolver()
    await db.execute(sa.schema.CreateTable(items))
    for i in range(rows):
        await Builder(items, db).insert({"group": "g", "value": i})
    return db


async def test_cursor_paginate_walks_a_table_in_stable_pages() -> None:
    db = await _seed(25)
    try:
        page1 = await Builder(items, db).order_by("id").cursor_paginate(per_page=10)
        assert isinstance(page1, CursorPaginator)
        assert len(page1) == 10
        assert page1.on_first_page() is True
        assert page1.has_more_pages() is True
        assert [r["id"] for r in page1] == list(range(1, 11))

        page2 = (
            await Builder(items, db)
            .order_by("id")
            .cursor_paginate(per_page=10, cursor=page1.next_cursor())
        )
        assert [r["id"] for r in page2] == list(range(11, 21))
        assert page2.has_more_pages() is True

        page3 = (
            await Builder(items, db)
            .order_by("id")
            .cursor_paginate(per_page=10, cursor=page2.next_cursor())
        )
        assert [r["id"] for r in page3] == list(range(21, 26))
        assert page3.has_more_pages() is False
        assert page3.next_cursor() is None
    finally:
        await db.dispose()


async def test_cursor_paginate_no_dup_or_gap_across_all_pages() -> None:
    db = await _seed(25)
    try:
        seen: list[int] = []
        cursor = None
        for _ in range(10):  # generous ceiling; 3 pages expected
            page = (
                await Builder(items, db).order_by("id").cursor_paginate(per_page=10, cursor=cursor)
            )
            seen.extend(r["id"] for r in page)
            if not page.has_more_pages():
                break
            cursor = page.next_cursor()
        assert seen == list(range(1, 26))
    finally:
        await db.dispose()


async def test_cursor_paginate_previous_cursor_walks_back() -> None:
    db = await _seed(25)
    try:
        page1 = await Builder(items, db).order_by("id").cursor_paginate(per_page=10)
        page2 = (
            await Builder(items, db)
            .order_by("id")
            .cursor_paginate(per_page=10, cursor=page1.next_cursor())
        )
        assert page2.previous_cursor() is not None

        back_to_page1 = (
            await Builder(items, db)
            .order_by("id")
            .cursor_paginate(per_page=10, cursor=page2.previous_cursor())
        )
        assert [r["id"] for r in back_to_page1] == [r["id"] for r in page1]
    finally:
        await db.dispose()


async def test_cursor_paginate_ties_are_stable_via_pk_tiebreak() -> None:
    """Ordering by a non-unique column (`group`, all equal here) alone would risk drift; the
    primary key is appended as an implicit tiebreaker so paging is still gap/dup-free."""
    db = await _seed(25)
    try:
        seen: list[int] = []
        cursor = None
        for _ in range(10):
            page = (
                await Builder(items, db)
                .order_by("group")
                .cursor_paginate(per_page=7, cursor=cursor)
            )
            seen.extend(r["id"] for r in page)
            if not page.has_more_pages():
                break
            cursor = page.next_cursor()
        assert sorted(seen) == list(range(1, 26))
        assert len(seen) == len(set(seen))  # no id repeated across pages
    finally:
        await db.dispose()


async def test_cursor_paginate_to_dict_matches_json_shape() -> None:
    db = await _seed(3)
    try:
        page = await Builder(items, db).order_by("id").cursor_paginate(per_page=10)
        data = page.to_dict()
        assert set(data) == {
            "data",
            "path",
            "per_page",
            "next_cursor",
            "next_page_url",
            "prev_cursor",
            "prev_page_url",
        }
        assert data["per_page"] == 10
        assert data["next_cursor"] is None
        assert len(data["data"]) == 3
    finally:
        await db.dispose()


async def test_cursor_paginate_defaults_to_primary_key_order_when_unordered() -> None:
    db = await _seed(5)
    try:
        page = await Builder(items, db).cursor_paginate(per_page=2)
        assert [r["id"] for r in page] == [1, 2]
    finally:
        await db.dispose()


def test_malformed_cursor_degrades_to_first_page_not_500() -> None:
    # untrusted query input (rule 20): garbage must not raise, it resolves to first-page
    for bad in ("not-base64!!", "YWJj", "", "eyJiYWQiOjF9"):
        assert decode_cursor(bad) == ({}, False)
