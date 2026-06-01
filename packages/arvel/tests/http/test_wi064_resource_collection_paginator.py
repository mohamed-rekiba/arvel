"""``ResourceCollection(paginator)`` integration.

When ``JsonResource.collection(...)`` is called with a paginator instead of a
plain list, the resulting envelope is the paginator's ``{data, meta, links}``
shape with each item transformed by the resource class. URL-aware ``request``
objects (Starlette-style) get HATEOAS-style URLs in ``links``; opaque/dummy
requests fall back to integer page numbers.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from arvel.database.paginator import Paginator
from arvel.database.query import CursorPaginator, SimplePaginator
from arvel.http.resources import JsonResource, ResourceCollection


class _User:
    """Stand-in domain object — anything with attributes works."""

    def __init__(self, *, user_id: int, email: str) -> None:
        self.user_id = user_id
        self.email = email


class UserResource(JsonResource[_User]):
    def to_dict(self, request: Any) -> dict[str, object]:
        return {"id": self.resource.user_id, "email": self.resource.email}


class _StarletteLikeURL:
    """Just enough of starlette.URL for the resource collection's purposes."""

    def __init__(self, scheme: str, netloc: str, path: str) -> None:
        self.scheme = scheme
        self.netloc = netloc
        self.path = path


class _StarletteLikeRequest:
    """Minimum Starlette/FastAPI Request surface the collection introspects."""

    def __init__(self, *, path: str = "/api/users", query: dict[str, str] | None = None) -> None:
        self.url = _StarletteLikeURL("https", "api.example.com", path)
        self.query_params = dict(query or {})


class _DummyRequest:
    """No ``url`` / ``query_params`` attributes — exercises the fallback path."""


def _parse(url: str) -> tuple[str, dict[str, list[str]]]:
    parts = urlsplit(url)
    base = f"{parts.scheme}://{parts.netloc}{parts.path}"
    return base, parse_qs(parts.query)


# Paginator (page-number, has total)


class TestPaginatorCollection:
    def _users(self) -> list[_User]:
        return [_User(user_id=1, email="a@x.io"), _User(user_id=2, email="b@x.io")]

    def test_collection_accepts_paginator(self) -> None:
        page: Paginator[_User] = Paginator(
            items=self._users(), total=42, per_page=2, current_page=3
        )
        coll = UserResource.collection(page)
        assert isinstance(coll, ResourceCollection)

    def test_envelope_has_data_meta_links(self) -> None:
        page: Paginator[_User] = Paginator(
            items=self._users(), total=42, per_page=2, current_page=3
        )
        body = UserResource.collection(page).to_dict(_DummyRequest())
        assert set(body.keys()) == {"data", "meta", "links"}

    def test_items_are_transformed_by_resource_class(self) -> None:
        page: Paginator[_User] = Paginator(
            items=self._users(), total=42, per_page=2, current_page=3
        )
        body = UserResource.collection(page).to_dict(_DummyRequest())
        assert body["data"] == [
            {"id": 1, "email": "a@x.io"},
            {"id": 2, "email": "b@x.io"},
        ]

    def test_meta_carries_paginator_state(self) -> None:
        page: Paginator[_User] = Paginator(
            items=self._users(), total=42, per_page=2, current_page=3
        )
        body = UserResource.collection(page).to_dict(_DummyRequest())
        assert body["meta"] == {
            "total": 42,
            "per_page": 2,
            "current_page": 3,
            "last_page": 21,
            "from": 5,
            "to": 6,
        }

    def test_links_are_integers_without_url_context(self) -> None:
        page: Paginator[_User] = Paginator(
            items=self._users(), total=42, per_page=2, current_page=3
        )
        body = UserResource.collection(page).to_dict(_DummyRequest())
        assert body["links"] == {"first": 1, "prev": 2, "next": 4, "last": 21}

    def test_links_are_urls_when_request_is_starlette_like(self) -> None:
        page: Paginator[_User] = Paginator(
            items=self._users(), total=42, per_page=2, current_page=3
        )
        req = _StarletteLikeRequest(path="/api/users", query={"sort": "id"})
        body = UserResource.collection(page).to_dict(req)
        first_url, first_q = _parse(body["links"]["first"])
        assert first_url == "https://api.example.com/api/users"
        assert first_q == {"sort": ["id"], "page": ["1"]}
        next_url, next_q = _parse(body["links"]["next"])
        assert next_url == "https://api.example.com/api/users"
        assert next_q == {"sort": ["id"], "page": ["4"]}

    def test_request_page_param_is_dropped_from_link_query(self) -> None:
        page: Paginator[_User] = Paginator(
            items=self._users(), total=42, per_page=2, current_page=3
        )
        # User landed on this view via /api/users?sort=id&page=3.
        # The paginator owns ``page`` — links must not carry the inbound page.
        req = _StarletteLikeRequest(path="/api/users", query={"sort": "id", "page": "3"})
        body = UserResource.collection(page).to_dict(req)
        _, first_q = _parse(body["links"]["first"])
        assert first_q == {"sort": ["id"], "page": ["1"]}

    def test_prev_is_none_on_first_page(self) -> None:
        page: Paginator[_User] = Paginator(
            items=self._users(), total=42, per_page=2, current_page=1
        )
        body = UserResource.collection(page).to_dict(_StarletteLikeRequest())
        assert body["links"]["prev"] is None

    def test_next_is_none_on_last_page(self) -> None:
        page: Paginator[_User] = Paginator(
            items=[_User(user_id=41, email="z@x.io")],
            total=41,
            per_page=2,
            current_page=21,
        )
        body = UserResource.collection(page).to_dict(_StarletteLikeRequest())
        assert body["links"]["next"] is None


# SimplePaginator (no total, just prev/next)


class TestSimplePaginatorCollection:
    def test_envelope_has_prev_and_next_only(self) -> None:
        page = SimplePaginator(
            items=[_User(user_id=1, email="a@x.io")],
            per_page=10,
            current_page=2,
            has_more=True,
        )
        body = UserResource.collection(page).to_dict(_DummyRequest())
        assert body["meta"] == {"total": None, "per_page": 10, "current_page": 2}
        assert body["links"] == {"prev": 1, "next": 3}

    def test_links_are_urls_with_starlette_request(self) -> None:
        page = SimplePaginator(
            items=[_User(user_id=1, email="a@x.io")],
            per_page=10,
            current_page=2,
            has_more=True,
        )
        req = _StarletteLikeRequest(path="/api/users", query={"q": "alice"})
        body = UserResource.collection(page).to_dict(req)
        prev_url, prev_q = _parse(body["links"]["prev"])
        assert prev_url == "https://api.example.com/api/users"
        assert prev_q == {"q": ["alice"], "page": ["1"]}

    def test_no_more_pages_sets_next_to_none(self) -> None:
        page: SimplePaginator[_User] = SimplePaginator(
            items=[],
            per_page=10,
            current_page=1,
            has_more=False,
        )
        body = UserResource.collection(page).to_dict(_StarletteLikeRequest())
        assert body["links"]["next"] is None
        assert body["links"]["prev"] is None


# CursorPaginator (opaque cursor)


class TestCursorPaginatorCollection:
    def test_envelope_has_next_cursor_in_links(self) -> None:
        page = CursorPaginator(
            items=[_User(user_id=1, email="a@x.io")],
            per_page=10,
            next_cursor="eyJpZCI6IDF9",
        )
        body = UserResource.collection(page).to_dict(_DummyRequest())
        # No URL context → the raw cursor token is the link value. prev is None (first page).
        assert body["links"] == {"prev": None, "next": "eyJpZCI6IDF9"}
        assert body["meta"] == {"per_page": 10, "has_more": True}
        assert body["data"] == [{"id": 1, "email": "a@x.io"}]

    def test_next_link_becomes_url_with_starlette_request(self) -> None:
        page = CursorPaginator(
            items=[_User(user_id=1, email="a@x.io")],
            per_page=10,
            next_cursor="eyJpZCI6IDF9",
        )
        req = _StarletteLikeRequest(path="/api/users", query={"sort": "id"})
        body = UserResource.collection(page).to_dict(req)
        next_url, next_q = _parse(body["links"]["next"])
        assert next_url == "https://api.example.com/api/users"
        assert next_q == {"sort": ["id"], "cursor": ["eyJpZCI6IDF9"]}

    def test_exhausted_cursor_returns_none(self) -> None:
        page: CursorPaginator[_User] = CursorPaginator(items=[], per_page=10, next_cursor=None)
        body = UserResource.collection(page).to_dict(_StarletteLikeRequest())
        assert body["links"]["next"] is None


# Regression — list-based collection still works unchanged


class TestListCollectionRegression:
    def test_list_envelope_is_data_only(self) -> None:
        users = [_User(user_id=1, email="a@x.io")]
        body = UserResource.collection(users).to_dict(_DummyRequest())
        assert body == {"data": [{"id": 1, "email": "a@x.io"}]}

    def test_wrap_override_still_works(self) -> None:
        class _Coll(ResourceCollection[_User]):
            def wrap(self, data: list[dict[str, Any]]) -> dict[str, Any]:
                return {"data": data, "meta": {"count": len(data)}}

        body = _Coll([_User(user_id=1, email="a@x.io")], UserResource).to_dict(_DummyRequest())
        assert body == {"data": [{"id": 1, "email": "a@x.io"}], "meta": {"count": 1}}


# Sanity: paginator path still accepts kwarg overrides for items_serializer
# (i.e. nothing we add breaks the underlying Paginator surface).


def test_underlying_paginator_to_dict_still_callable_directly() -> None:
    """Sanity check — the resource collection layer must not corrupt or shadow
    the paginator's own ``to_dict``."""
    page: Paginator[_User] = Paginator(
        items=[_User(user_id=1, email="a@x.io")], total=1, per_page=10, current_page=1
    )
    raw = page.to_dict(items_serializer=lambda u: {"id": u.user_id})
    assert raw["data"] == [{"id": 1}]


def test_collection_with_paginator_keeps_resource_class_generic() -> None:
    """Smoke: collection() inferred T == _User; runtime check via __orig_class__
    is unreliable, so just verify behavior is type-safe at the call site.
    """
    from typing import cast as _cast

    page: Paginator[_User] = Paginator(
        items=[_User(user_id=1, email="a@x.io")], total=1, per_page=10, current_page=1
    )
    coll = UserResource.collection(page)
    body = coll.to_dict(_DummyRequest())
    data = _cast("list[dict[str, object]]", body["data"])
    # id and email are the two fields the resource emits — nothing else leaked.
    assert set(data[0].keys()) == {"id", "email"}


def test_rejects_neither_list_nor_paginator() -> None:
    """Passing something that is not a list and not a paginator raises early."""
    with pytest.raises(TypeError):
        UserResource.collection("not a list or paginator")  # type: ignore[arg-type]
