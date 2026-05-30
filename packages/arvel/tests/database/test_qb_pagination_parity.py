"""Eloquent-parity (backlog 005, S11/S9): pagination HTTP + JSON parity.

page_name + request page resolution, Laravel flat envelope, bidirectional cursors,
appends/with_query_string/fragment, on_each_side link window.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from arvel.database import Model
from arvel.database.paginator import (
    PaginationRequest,
    Paginator,
    reset_pagination_request,
    set_pagination_request,
)
from sqlalchemy import Integer, String
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column


class PgItem(Model):
    __tablename__ = "pg_items"
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, init=False, default=None
    )
    name: Mapped[str] = mapped_column(String(40), nullable=False)


async def _seed(engine: AsyncEngine, n: int) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)
    for i in range(n):
        await PgItem.create(name=f"i{i:02d}")


def _q(url: str | None) -> dict[str, list[str]]:
    return parse_qs(urlparse(url or "").query)


# ── request page resolution ──────────────────────────────────────────────────


async def test_paginate_resolves_page_from_request(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _seed(engine, 25)
    token = set_pagination_request(PaginationRequest(path="/items", query={"page": "2"}))
    try:
        page = await PgItem.order_by(PgItem.id).paginate(per_page=10)
    finally:
        reset_pagination_request(token)
    assert page.current_page == 2
    assert len(page.items) == 10


async def test_paginate_custom_page_name(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine, 25)
    token = set_pagination_request(PaginationRequest(path="/items", query={"p": "3"}))
    try:
        page = await PgItem.order_by(PgItem.id).paginate(per_page=10, page_name="p")
    finally:
        reset_pagination_request(token)
    assert page.current_page == 3


# ── Laravel flat envelope ─────────────────────────────────────────────────────


def test_to_response_flat_envelope_shape() -> None:
    p: Paginator[int] = Paginator(
        items=list(range(10)), total=53, per_page=10, current_page=2, path="/posts"
    )
    body = p.to_response()
    assert body["current_page"] == 2
    assert body["total"] == 53
    assert body["last_page"] == 6
    assert body["from"] == 11
    assert body["to"] == 20
    assert body["path"] == "/posts"
    assert _q(body["next_page_url"])["page"] == ["3"]
    assert _q(body["prev_page_url"])["page"] == ["1"]
    assert body["first_page_url"].endswith("page=1")
    assert _q(body["last_page_url"])["page"] == ["6"]
    # links array carries the Previous/Next bookends + active flag
    labels = [link["label"] for link in body["links"]]
    assert labels[0] == "&laquo; Previous"
    assert labels[-1] == "Next &raquo;"
    active = [link for link in body["links"] if link["active"]]
    assert len(active) == 1
    assert active[0]["label"] == "2"


def test_to_response_on_each_side_window() -> None:
    p: Paginator[int] = Paginator(
        items=[], total=500, per_page=10, current_page=25, path="/x", on_each_side=1
    )
    body = p.to_response()
    page_labels = [link["label"] for link in body["links"]]
    assert "..." in page_labels  # large set elides with gaps
    assert "1" in page_labels
    assert "50" in page_labels


# ── appends / with_query_string / fragment ────────────────────────────────────


def test_appends_preserves_query_params() -> None:
    p: Paginator[int] = Paginator(items=[], total=30, per_page=10, current_page=1, path="/posts")
    body = p.appends({"sort": "-name", "tag": "py"}).to_response()
    nxt = _q(body["next_page_url"])
    assert nxt["page"] == ["2"]
    assert nxt["sort"] == ["-name"]
    assert nxt["tag"] == ["py"]


def test_with_query_string_pulls_request_query() -> None:
    token = set_pagination_request(
        PaginationRequest(path="/posts", query={"sort": "asc", "page": "1"})
    )
    try:
        p: Paginator[int] = Paginator(items=[], total=30, per_page=10, current_page=1)
        body = p.with_query_string().to_response()
    finally:
        reset_pagination_request(token)
    nxt = _q(body["next_page_url"])
    assert nxt["sort"] == ["asc"]
    # the page key is owned by the paginator, not duplicated from the request
    assert nxt["page"] == ["2"]


def test_fragment_appends_hash() -> None:
    p: Paginator[int] = Paginator(items=[], total=30, per_page=10, current_page=1, path="/posts")
    body = p.fragment("results").to_response()
    assert body["next_page_url"].endswith("#results")


# ── bidirectional cursors ─────────────────────────────────────────────────────


async def test_cursor_paginate_emits_both_cursors(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _seed(engine, 12)
    first = await PgItem.order_by(PgItem.id).cursor_paginate(per_page=4)
    assert first.prev_cursor is None  # first page has no previous
    assert first.next_cursor is not None

    second = await PgItem.order_by(PgItem.id).cursor_paginate(
        per_page=4, cursor=first.next_cursor
    )
    assert second.prev_cursor is not None
    assert second.next_cursor is not None
    # second page continues right after the first
    assert min(i.id for i in second.items) > max(i.id for i in first.items)


async def test_cursor_paginate_previous_page_round_trips(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _seed(engine, 12)
    first = await PgItem.order_by(PgItem.id).cursor_paginate(per_page=4)
    second = await PgItem.order_by(PgItem.id).cursor_paginate(
        per_page=4, cursor=first.next_cursor
    )
    # walk back from the second page using its prev_cursor
    back = await PgItem.order_by(PgItem.id).cursor_paginate(
        per_page=4, cursor=second.prev_cursor
    )
    assert [i.id for i in back.items] == [i.id for i in first.items]


async def test_cursor_response_envelope(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine, 12)
    token = set_pagination_request(PaginationRequest(path="/items", query={}))
    try:
        first = await PgItem.order_by(PgItem.id).cursor_paginate(per_page=4)
        body = first.to_response()
    finally:
        reset_pagination_request(token)
    assert body["path"] == "/items"
    assert body["next_cursor"] == first.next_cursor
    assert body["prev_cursor"] is None
    assert _q(body["next_page_url"])["cursor"] == [first.next_cursor]
