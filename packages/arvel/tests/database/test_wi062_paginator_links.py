"""Paginator.links returns URL strings.

`Paginator.to_dict` puts integer page numbers in `links` — fine for math,
useless for HATEOAS clients. `Paginator.links(base_url, *, query=None)` builds
the {first, prev, next, last} URL dict, encoding the `page` query parameter
and preserving any caller-supplied filters."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from arvel.database.paginator import Paginator
from arvel.database.query import SimplePaginator


def _paginator(*, current: int, total: int = 53, per_page: int = 10) -> Paginator[int]:
    return Paginator(
        items=list(range(per_page)),
        total=total,
        per_page=per_page,
        current_page=current,
    )


def _parse_query(url: str | None) -> dict[str, list[str]]:
    """Return the query-string params of ``url`` as a dict for membership asserts."""
    return parse_qs(urlparse(url or "").query)


class TestPaginatorLinks:
    def test_first_page_has_no_prev(self) -> None:
        p = _paginator(current=1)
        links = p.links("https://api.example.com/posts")
        assert links == {
            "first": "https://api.example.com/posts?page=1",
            "prev": None,
            "next": "https://api.example.com/posts?page=2",
            "last": "https://api.example.com/posts?page=6",
        }

    def test_middle_page_has_both_neighbours(self) -> None:
        p = _paginator(current=3)
        links = p.links("https://api.example.com/posts")
        assert links["first"] == "https://api.example.com/posts?page=1"
        assert links["prev"] == "https://api.example.com/posts?page=2"
        assert links["next"] == "https://api.example.com/posts?page=4"
        assert links["last"] == "https://api.example.com/posts?page=6"

    def test_last_page_has_no_next(self) -> None:
        p = _paginator(current=6)
        links = p.links("https://api.example.com/posts")
        assert links["prev"] == "https://api.example.com/posts?page=5"
        assert links["next"] is None
        assert links["last"] == "https://api.example.com/posts?page=6"

    def test_single_page_when_empty(self) -> None:
        p: Paginator[int] = Paginator(items=[], total=0, per_page=10, current_page=1)
        links = p.links("https://api.example.com/posts")
        assert links == {
            "first": "https://api.example.com/posts?page=1",
            "prev": None,
            "next": None,
            "last": "https://api.example.com/posts?page=1",
        }

    def test_preserves_caller_query_params(self) -> None:
        p = _paginator(current=2)
        links = p.links(
            "https://api.example.com/posts",
            query={"sort": "-published_at", "tag": "python"},
        )
        # Order of params in the URL is stable but not necessarily alphabetical;
        # parse to assert by membership.
        params = _parse_query(links["next"])
        assert params["page"] == ["3"]
        assert params["sort"] == ["-published_at"]
        assert params["tag"] == ["python"]

    def test_caller_query_param_named_page_is_overridden(self) -> None:
        # If the caller passes an existing page param it must be replaced —
        # otherwise the URL has two page= entries.
        p = _paginator(current=2)
        links = p.links("https://api.example.com/posts", query={"page": "999", "sort": "asc"})
        params = _parse_query(links["first"])
        assert params["page"] == ["1"]
        assert params["sort"] == ["asc"]

    def test_base_url_with_trailing_slash_normalised(self) -> None:
        p = _paginator(current=1)
        links = p.links("https://api.example.com/posts/")
        # No double slash before the query string.
        assert "//?" not in (links["first"] or "")
        assert (links["first"] or "").startswith("https://api.example.com/posts?")

    def test_base_url_with_existing_query_string_merged(self) -> None:
        p = _paginator(current=2)
        links = p.links("https://api.example.com/posts?tag=python")
        params = _parse_query(links["next"])
        assert params["page"] == ["3"]
        assert params["tag"] == ["python"]


class TestPaginatorToDictWithUrls:
    def test_to_dict_default_uses_integer_page_numbers(self) -> None:
        # Backward compatible — no base_url → existing integer links shape.
        p = _paginator(current=2)
        result = p.to_dict()
        assert result["links"]["first"] == 1
        assert result["links"]["prev"] == 1
        assert result["links"]["next"] == 3
        assert result["links"]["last"] == 6

    def test_to_dict_with_base_url_emits_url_strings(self) -> None:
        p = _paginator(current=2)
        result = p.to_dict(base_url="https://api.example.com/posts")
        assert result["links"]["first"] == "https://api.example.com/posts?page=1"
        assert result["links"]["prev"] == "https://api.example.com/posts?page=1"
        assert result["links"]["next"] == "https://api.example.com/posts?page=3"
        assert result["links"]["last"] == "https://api.example.com/posts?page=6"

    def test_to_dict_with_base_url_and_extra_query(self) -> None:
        p = _paginator(current=1)
        result = p.to_dict(base_url="https://api.example.com/posts", query={"sort": "desc"})
        params = _parse_query(result["links"]["next"])
        assert params["page"] == ["2"]
        assert params["sort"] == ["desc"]


class TestSimplePaginatorLinks:
    def test_simple_paginator_links_has_only_prev_next(self) -> None:
        p: SimplePaginator[int] = SimplePaginator(
            items=[1, 2, 3], per_page=3, current_page=2, has_more=True
        )
        links = p.links("https://api.example.com/feed")
        assert links == {
            "prev": "https://api.example.com/feed?page=1",
            "next": "https://api.example.com/feed?page=3",
        }

    def test_simple_paginator_first_page_no_prev(self) -> None:
        p: SimplePaginator[int] = SimplePaginator(
            items=[1], per_page=3, current_page=1, has_more=True
        )
        links = p.links("https://api.example.com/feed")
        assert links["prev"] is None
        assert links["next"] == "https://api.example.com/feed?page=2"

    def test_simple_paginator_last_page_no_next(self) -> None:
        p: SimplePaginator[int] = SimplePaginator(
            items=[1], per_page=3, current_page=5, has_more=False
        )
        links = p.links("https://api.example.com/feed")
        assert links["prev"] == "https://api.example.com/feed?page=4"
        assert links["next"] is None


@pytest.mark.parametrize(
    ("current", "total", "per_page", "expected_last_url_page"),
    [
        (1, 10, 5, 2),
        (1, 11, 5, 3),
        (1, 9, 5, 2),
        (1, 5, 5, 1),
        (1, 1, 10, 1),
    ],
)
def test_paginator_last_url_matches_last_page(
    current: int, total: int, per_page: int, expected_last_url_page: int
) -> None:
    p: Paginator[int] = Paginator(items=[], total=total, per_page=per_page, current_page=current)
    links = p.links("https://api.example.com/x")
    assert links["last"] == f"https://api.example.com/x?page={expected_last_url_page}"
