"""Pagination — Laravel-parity LengthAwarePaginator + simple Paginator.

Covers the accessor surface, URL building (incl. per-request resolvers + query string +
fragment), the numbered link window, the Laravel JSON shape, simple prev/next semantics,
iteration, model-item serialization, and HTML rendering through the real view factory +
shipped ``pagination`` namespace. Builder integration is exercised against real sqlite.
"""

from __future__ import annotations

import sqlalchemy as sa

from arvel.http.request import Request, current_request
from arvel.pagination import (
    LengthAwarePaginator,
    Paginator,
    resolve_current_page,
    resolve_current_path,
)

# --- LengthAwarePaginator: accessors ------------------------------------------------


def _page(items: list[int], total: int, per_page: int, current: int) -> LengthAwarePaginator:
    return LengthAwarePaginator(items, total, per_page, current, path="/users")


def test_accessors_middle_page() -> None:
    p = _page([5, 6, 7, 8], total=23, per_page=4, current=2)
    assert p.total() == 23
    assert p.per_page() == 4
    assert p.current_page() == 2
    assert p.count() == 4
    assert p.last_page() == 6  # ceil(23 / 4)
    assert p.first_item() == 5  # (2-1)*4 + 1
    assert p.last_item() == 8
    assert p.has_pages() is True
    assert p.has_more_pages() is True
    assert p.on_first_page() is False
    assert p.is_empty() is False
    assert p.items().all() == [5, 6, 7, 8]


def test_single_page_has_no_pages() -> None:
    p = _page([1, 2], total=2, per_page=15, current=1)
    assert p.last_page() == 1
    assert p.has_pages() is False
    assert p.has_more_pages() is False
    assert p.on_first_page() is True


def test_last_page_no_more() -> None:
    p = _page([21, 22, 23], total=23, per_page=4, current=6)
    assert p.has_more_pages() is False
    assert p.next_page_url() is None
    assert p.last_item() == 23  # short final page


def test_empty_page_items_are_none() -> None:
    p = _page([], total=0, per_page=15, current=1)
    assert p.first_item() is None
    assert p.last_item() is None
    assert p.is_empty() is True


# --- URL building -------------------------------------------------------------------


def test_url_building_and_neighbours() -> None:
    p = _page([5, 6], total=23, per_page=4, current=2)
    assert p.url(3) == "/users?page=3"
    assert p.previous_page_url() == "/users?page=1"
    assert p.next_page_url() == "/users?page=3"


def test_url_clamps_non_positive_page() -> None:
    p = _page([1], total=1, per_page=1, current=1)
    assert p.url(0) == "/users?page=1"
    assert p.url(-5) == "/users?page=1"


def test_per_page_zero_is_guarded() -> None:
    # per_page <= 0 would divide-by-zero in last_page — clamp to 1 (Laravel: per_page >= 1)
    p = LengthAwarePaginator([1], total=5, per_page=0, current_page=1, path="/x")
    assert p.per_page() == 1
    assert p.last_page() == 5  # no ZeroDivisionError


def test_url_preserves_list_valued_appends() -> None:
    p = _page([1], total=10, per_page=2, current=1)
    p.append("tag", ["a", "b"])
    url = p.url(2)
    assert "tag=a" in url and "tag=b" in url  # repeated params, not a stringified list
    assert "%5B" not in url  # no "[" — the list was not stringified


def test_appends_and_fragment() -> None:
    p = _page([1], total=10, per_page=1, current=2)
    p.appends({"sort": "name"}).append("filter", "active").fragment("results")
    url = p.url(3)
    assert url.startswith("/users?")
    assert "sort=name" in url
    assert "filter=active" in url
    assert "page=3" in url
    assert url.endswith("#results")
    assert p.fragment() == "results"


# --- numbered link window -----------------------------------------------------------


def test_window_small_is_single_band() -> None:
    p = _page([1], total=50, per_page=10, current=2)  # last_page == 5 < window+8
    elements = p.elements()
    assert len(elements) == 1
    assert list(elements[0].keys()) == [1, 2, 3, 4, 5]


def test_window_large_has_separators() -> None:
    p = _page([1], total=1000, per_page=10, current=50)  # last_page == 100
    elements = p.elements()
    # first band ... slider ... last band
    assert elements[0] == {1: p.url(1), 2: p.url(2)}
    assert "..." in elements
    assert 100 in elements[-1]
    # slider centered on current with on_each_side==3
    slider = elements[2]
    assert min(slider) == 47 and max(slider) == 53


def test_window_near_start_and_near_end() -> None:
    near_start = _page([1], total=1000, per_page=10, current=3)  # current <= window
    e1 = near_start.elements()
    assert 1 in e1[0] and e1[1] == "..." and 100 in e1[-1]
    near_end = _page([1], total=1000, per_page=10, current=98)  # current > last - window
    e2 = near_end.elements()
    assert e2[0] == {1: near_end.url(1), 2: near_end.url(2)} and e2[1] == "..." and 100 in e2[-1]


def test_on_each_side_widens_window() -> None:
    p = _page([1], total=1000, per_page=10, current=50)
    assert p.on_each_side(1) is p  # fluent
    slider = p.elements()[2]
    assert min(slider) == 49 and max(slider) == 51


def test_to_dict_links_include_separator_for_large_set() -> None:
    p = _page([1], total=1000, per_page=10, current=50)
    labels = [link["label"] for link in p.to_dict()["links"]]
    assert "..." in labels  # the separator is emitted as a null-url placeholder link


def test_page_name_accessors() -> None:
    p = _page([1], total=10, per_page=2, current=1)
    assert p.get_page_name() == "page"
    assert p.set_page_name("p") is p
    assert p.get_page_name() == "p"
    assert p.url(2) == "/users?p=2"
    assert p.is_not_empty() is True


# --- Laravel JSON shape -------------------------------------------------------------


def test_to_dict_laravel_shape() -> None:
    p = _page([5, 6, 7, 8], total=23, per_page=4, current=2)
    d = p.to_dict()
    assert d["current_page"] == 2
    assert d["data"] == [5, 6, 7, 8]
    assert d["first_page_url"] == "/users?page=1"
    assert d["from"] == 5
    assert d["to"] == 8
    assert d["last_page"] == 6
    assert d["last_page_url"] == "/users?page=6"
    assert d["next_page_url"] == "/users?page=3"
    assert d["prev_page_url"] == "/users?page=1"
    assert d["path"] == "/users"
    assert d["per_page"] == 4
    assert d["total"] == 23
    # the flat links array: Previous, page numbers, Next
    labels = [link["label"] for link in d["links"]]
    assert labels[0] == "&laquo; Previous"
    assert labels[-1] == "Next &raquo;"
    active = [link for link in d["links"] if link["active"]]
    assert len(active) == 1 and active[0]["label"] == "2"


def test_to_dict_serializes_model_items() -> None:
    class _Row:
        def __init__(self, v: int) -> None:
            self.v = v

        def to_dict(self) -> dict[str, int]:
            return {"v": self.v}

    p = LengthAwarePaginator([_Row(1), _Row(2)], total=2, per_page=15, current_page=1, path="/x")
    assert p.to_dict()["data"] == [{"v": 1}, {"v": 2}]


# --- iteration ----------------------------------------------------------------------


def test_iteration_and_indexing() -> None:
    p = _page([10, 20, 30], total=3, per_page=15, current=1)
    assert list(p) == [10, 20, 30]
    assert len(p) == 3
    assert p[1] == 20


# --- simple Paginator ---------------------------------------------------------------


def test_simple_infers_more_from_extra_row() -> None:
    # fetched per_page+1 == 3 rows for per_page 2 → there IS a next page, extra trimmed
    p = Paginator([1, 2, 3], per_page=2, current_page=1, path="/p")
    assert p.count() == 2
    assert p.has_more_pages() is True
    assert p.next_page_url() == "/p?page=2"
    assert p.previous_page_url() is None


def test_simple_last_page_no_more() -> None:
    p = Paginator([1, 2], per_page=2, current_page=2, path="/p")  # exactly per_page → no extra
    assert p.has_more_pages() is False
    assert p.next_page_url() is None
    assert p.previous_page_url() == "/p?page=1"


def test_simple_has_pages() -> None:
    first = Paginator([1, 2, 3], per_page=2, current_page=1, path="/p")  # has a next page
    assert first.has_pages() is True
    only = Paginator([1, 2], per_page=2, current_page=1, path="/p")  # single page, no next
    assert only.has_pages() is False


def test_simple_explicit_has_more_flag_skips_trim() -> None:
    p = Paginator([1, 2, 3], per_page=2, current_page=1, has_more=False, path="/p")
    assert p.count() == 3  # not trimmed when has_more is explicit
    assert p.has_more_pages() is False


def test_simple_to_dict_has_no_total() -> None:
    p = Paginator([1, 2, 3], per_page=2, current_page=1, path="/p")
    d = p.to_dict()
    assert "total" not in d
    assert "last_page" not in d
    assert d["next_page_url"] == "/p?page=2"
    assert d["data"] == [1, 2]


# --- per-request resolvers ----------------------------------------------------------


class _FakeURL:
    def __init__(self, path: str) -> None:
        self.path = path


class _FakeRequest:
    def __init__(self, path: str, params: dict[str, str]) -> None:
        self.url = _FakeURL(path)
        self.query_params = params


def test_resolvers_default_outside_request() -> None:
    assert resolve_current_page() == 1
    assert resolve_current_path() == "/"


def test_resolvers_read_from_bound_request() -> None:
    token = current_request.set(Request(_FakeRequest("/posts", {"page": "4"})))
    try:
        assert resolve_current_page() == 4
        assert resolve_current_path() == "/posts"
        # a paginator created without explicit page/path picks these up
        p = LengthAwarePaginator([1], total=100, per_page=10)
        assert p.current_page() == 4
        assert p.path() == "/posts"
        assert p.url(2) == "/posts?page=2"
    finally:
        current_request.reset(token)


def test_resolver_clamps_bad_page() -> None:
    token = current_request.set(Request(_FakeRequest("/x", {"page": "-3"})))
    try:
        assert resolve_current_page() == 1
    finally:
        current_request.reset(token)
    token = current_request.set(Request(_FakeRequest("/x", {"page": "abc"})))
    try:
        assert resolve_current_page() == 1
    finally:
        current_request.reset(token)


def test_with_query_string_pulls_request_params() -> None:
    token = current_request.set(Request(_FakeRequest("/s", {"page": "2", "q": "django"})))
    try:
        p = LengthAwarePaginator([1], total=100, per_page=10)
        p.with_query_string()
        url = p.url(3)
        assert "q=django" in url
        assert "page=3" in url
        assert "page=2" not in url  # the page key is excluded then re-set
    finally:
        current_request.reset(token)


# --- Builder integration against real sqlite ----------------------------------------

_md = sa.MetaData()
_items = sa.Table(
    "paginate_items",
    _md,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("n", sa.Integer),
)


async def _seed_items(count: int) -> object:
    from arvel.database import Builder, ConnectionResolver

    db = ConnectionResolver()
    await db.execute(sa.schema.CreateTable(_items))
    for i in range(1, count + 1):
        await Builder(_items, db).insert({"n": i})
    return db


async def test_builder_paginate_returns_length_aware() -> None:
    from arvel.database import Builder

    db = await _seed_items(7)
    try:
        page = await Builder(_items, db).order_by("n").paginate(per_page=3, page=2)
        assert isinstance(page, LengthAwarePaginator)
        assert page.total() == 7
        assert page.last_page() == 3
        assert page.current_page() == 2
        assert [row["n"] for row in page] == [4, 5, 6]
        assert page.has_more_pages() is True
    finally:
        await db.dispose()


async def test_builder_simple_paginate_detects_next_without_count() -> None:
    from arvel.database import Builder

    db = await _seed_items(7)
    try:
        page = await Builder(_items, db).order_by("n").simple_paginate(per_page=3, page=1)
        assert isinstance(page, Paginator)
        assert page.count() == 3  # extra fetched row trimmed
        assert [row["n"] for row in page] == [1, 2, 3]
        assert page.has_more_pages() is True
        # last page: fewer than per_page+1 rows come back → no next page
        last = await Builder(_items, db).order_by("n").simple_paginate(per_page=3, page=3)
        assert last.count() == 1
        assert last.has_more_pages() is False
    finally:
        await db.dispose()


# --- HTML rendering through the real view factory + shipped namespace ----------------


def _app_with_pagination_views() -> None:
    """Bind a minimal app whose view factory carries the shipped ``pagination`` namespace."""
    from pathlib import Path

    import arvel.pagination
    from arvel.kernel import Application, set_application
    from arvel.views import ViewFactory

    factory = ViewFactory()
    views_dir = Path(arvel.pagination.__file__).parent / "views"
    factory.add_namespace("pagination", str(views_dir))
    app = Application()
    app.instance("view", factory)
    set_application(app)


async def test_links_renders_html_via_pagination_namespace() -> None:
    from arvel.kernel import set_application

    _app_with_pagination_views()
    try:
        p = _page([5, 6, 7, 8], total=23, per_page=4, current=2)
        html = await p.links()
        assert "<nav" in html
        assert 'href="/users?page=3"' in html  # next page link present
        assert "results" in html  # summary line rendered
        assert 'aria-current="page"' in html  # current page is a non-link
    finally:
        set_application(None)


async def test_links_empty_for_single_page() -> None:
    from arvel.kernel import set_application

    _app_with_pagination_views()
    try:
        p = _page([1, 2], total=2, per_page=15, current=1)
        html = await p.links()
        assert html.strip() == ""  # has_pages() is False → nothing rendered
    finally:
        set_application(None)
