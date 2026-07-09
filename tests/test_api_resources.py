"""API Resources (spec 08 §4
``ResourceCollection`` — ``when``/``when_loaded``/``merge_when``/``additional``, data-wrapping,
the paginator meta/links shape, and the HTTP kernel's resource-recognition (a route handler
returning a resource "just works", golden JSON)."""

from __future__ import annotations

from typing import Any, ClassVar

import sqlalchemy as sa
from litestar.testing import TestClient

from arvel.database import ConnectionResolver, Model
from arvel.database.resources import MISSING, JsonResource, ResourceCollection
from arvel.http import HttpKernel
from arvel.pagination import LengthAwarePaginator


class Author(Model):
    __fields__: ClassVar = {"name": str}
    __fillable__: ClassVar = ["name"]


class Post(Model):
    __fields__: ClassVar = {"title": str, "body": str, "author_id": int}
    __fillable__: ClassVar = ["title", "body", "author_id"]

    def author(self) -> Any:
        return self.belongs_to(Author)


class PostResource(JsonResource[Post]):
    def to_array(self, request: Any | None = None) -> dict[str, Any]:
        return {
            "id": self.resource.id,
            "title": self.resource.title,
            **self.merge_when(bool(self.resource.body), {"body": self.resource.body}),
            "author": self.when_loaded("author", lambda a: {"name": a.name}),
        }


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    Author.set_connection(db)
    Post.set_connection(db)
    await db.execute(sa.schema.CreateTable(Author.__table__))
    await db.execute(sa.schema.CreateTable(Post.__table__))
    return db


async def test_when_loaded_omits_unloaded_relation() -> None:
    db = await _setup()
    try:
        author = await Author.create(name="Ada")
        post = await Post.create(title="Hi", body="", author_id=author.id)
        fetched = await Post.find(post.id)
        assert fetched is not None
        payload = PostResource(fetched).to_payload()
        assert "author" not in payload["data"]
        assert "body" not in payload["data"]  # merge_when(False, ...) contributes nothing
    finally:
        await db.dispose()


async def test_when_loaded_includes_eager_loaded_relation() -> None:
    db = await _setup()
    try:
        author = await Author.create(name="Ada")
        await Post.create(title="Hi", body="text", author_id=author.id)
        fetched = (await Post.with_("author").get())[0]
        payload = PostResource(fetched).to_payload()
        assert payload["data"]["author"] == {"name": "Ada"}
        assert payload["data"]["body"] == "text"
    finally:
        await db.dispose()


def test_wrap_default_is_data_and_additional_merges_top_level() -> None:
    class Simple(JsonResource[dict[str, Any]]):
        def to_array(self, request: Any | None = None) -> dict[str, Any]:
            return {"id": self.resource["id"]}

    payload = Simple({"id": 1}).additional({"version": "v1"}).to_payload()
    assert payload == {"data": {"id": 1}, "version": "v1"}


def test_wrap_none_disables_wrapping_no_double_wrap() -> None:
    class Unwrapped(JsonResource[dict[str, Any]]):
        wrap: ClassVar[str | None] = None

        def to_array(self, request: Any | None = None) -> dict[str, Any]:
            return {"id": self.resource["id"]}

    assert Unwrapped({"id": 1}).to_payload() == {"id": 1}


def test_when_and_when_not_none_strip_missing() -> None:
    class Flagged(JsonResource[dict[str, Any]]):
        def to_array(self, request: Any | None = None) -> dict[str, Any]:
            return {
                "shown": self.when(True, "yes"),
                "hidden": self.when(False, "no"),
                "present": self.when_not_none("x"),
                "absent": self.when_not_none(None),
            }

    data = Flagged({}).to_array()
    assert data["hidden"] is MISSING and data["absent"] is MISSING
    payload = Flagged({}).to_payload()
    assert payload == {"data": {"shown": "yes", "present": "x"}}


def test_when_counted_present_only_when_the_count_was_loaded() -> None:
    from arvel.database.resources import ResourceTransformer

    class Loaded:
        _attributes: ClassVar = {"posts_count": 3}

    class Uncounted:
        _attributes: ClassVar = {}

    assert ResourceTransformer(Loaded()).when_counted("posts") == 3
    assert ResourceTransformer(Uncounted()).when_counted("posts") is MISSING
    assert ResourceTransformer(Loaded()).when_counted("posts", lambda c: c * 2) == 6


def test_when_pivot_loaded_present_only_with_a_pivot() -> None:
    from arvel.database.resources import ResourceTransformer

    class WithPivot:
        _attributes: ClassVar = {"pivot": {"note": "x"}}

    class NoPivot:
        _attributes: ClassVar = {}

    assert ResourceTransformer(WithPivot()).when_pivot_loaded() == {"note": "x"}
    assert ResourceTransformer(NoPivot()).when_pivot_loaded() is MISSING
    # honors an overridden accessor (BelongsToMany.as_) rather than hardcoding "pivot"
    assert ResourceTransformer(WithPivot()).when_pivot_loaded(accessor="assignment") is MISSING


def test_when_counted_and_when_pivot_loaded_are_stripped_by_to_payload() -> None:
    class Counted(JsonResource[dict[str, Any]]):
        def to_array(self, request: Any | None = None) -> dict[str, Any]:
            return {"posts_count": self.when_counted("posts")}

    class WithCount:
        _attributes: ClassVar = {"posts_count": 5}

    class NoCount:
        _attributes: ClassVar = {}

    assert Counted(WithCount()).to_payload() == {"data": {"posts_count": 5}}  # type: ignore[arg-type]
    assert Counted(NoCount()).to_payload() == {"data": {}}  # type: ignore[arg-type]


def test_collection_wraps_each_item_under_data() -> None:
    class Simple(JsonResource[dict[str, Any]]):
        def to_array(self, request: Any | None = None) -> dict[str, Any]:
            return {"id": self.resource["id"]}

    collection = Simple.collection([{"id": 1}, {"id": 2}])
    assert isinstance(collection, ResourceCollection)
    assert collection.to_payload() == {"data": [{"id": 1}, {"id": 2}]}


def test_resource_collection_from_paginator_has_meta_and_links_shape() -> None:
    class Simple(JsonResource[dict[str, Any]]):
        def to_array(self, request: Any | None = None) -> dict[str, Any]:
            return {"id": self.resource["id"]}

    paginator = LengthAwarePaginator(
        [{"id": 1}, {"id": 2}], total=5, per_page=2, current_page=1, path="/items"
    )
    payload = Simple.collection(paginator).to_payload()
    assert payload["data"] == [{"id": 1}, {"id": 2}]
    assert payload["meta"] == {
        "current_page": 1,
        "from": 1,
        "last_page": 3,
        "path": "/items",
        "per_page": 2,
        "to": 2,
        "total": 5,
    }
    assert set(payload["links"]) == {"first", "last", "prev", "next"}
    assert payload["links"]["prev"] is None
    assert payload["links"]["next"] is not None


async def test_route_returning_a_resource_serves_wrapped_json_through_scaffolded_app() -> None:
    db = await _setup()
    try:
        author = await Author.create(name="Ada")
        await Post.create(title="Hi", body="text", author_id=author.id)

        async def handler(request: Any) -> Any:
            post = (await Post.with_("author").get())[0]
            return PostResource(post)

        kernel = HttpKernel()
        kernel.get("/posts/first", handler)
        with TestClient(kernel.build()) as client:
            response = client.get("/posts/first")
            assert response.status_code == 200
            body = response.json()
        assert body["data"]["title"] == "Hi"
        assert body["data"]["author"] == {"name": "Ada"}
    finally:
        await db.dispose()
