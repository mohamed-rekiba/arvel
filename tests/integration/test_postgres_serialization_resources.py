"""Integration (E11) — JSON:API nested includes, the when_counted/when_pivot_loaded resource
helpers, and to_dict() date stringification, against a real Postgres (not just the FakeModel
unit shape in test_jsonapi_resources.py). Routes are hit over real HTTP via
``httpx.ASGITransport`` + ``httpx.AsyncClient`` (the tests/integration/test_reference_app.py
pattern) so the request handlers and the loop-bound asyncpg pool share the test's single event
loop — litestar's ``TestClient`` runs its own loop, which breaks a real asyncpg connection."""

from __future__ import annotations

from typing import Any, ClassVar

import httpx
import pytest
import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model
from arvel.database.resources import JsonApiResource, JsonResource
from arvel.http import HttpKernel

pytestmark = pytest.mark.integration


class IAuthor(Model):
    __table_name__ = "e11_authors"
    __fields__: ClassVar = {"name": str}
    __fillable__: ClassVar = ["name"]
    __timestamps__ = False

    def posts(self) -> Any:
        # explicit fk: the default inference snake-cases the class name (`IAuthor` ->
        # `i_author_id`), which doesn't match this table's plain `author_id` column
        return self.has_many(IPost, foreign_key="author_id")

    def comments(self) -> Any:
        return self.has_many(IComment, foreign_key="author_id")

    def roles(self) -> Any:
        return self.belongs_to_many(
            IRole,
            pivot="e11_author_role",
            foreign_pivot_key="author_id",
            related_pivot_key="role_id",
        ).with_pivot("note")


class IPost(Model):
    __table_name__ = "e11_posts"
    __fields__: ClassVar = {"title": str, "author_id": int}
    __fillable__: ClassVar = ["title", "author_id"]
    __timestamps__ = False

    def author(self) -> Any:
        # explicit fk: the default inference snake-cases the related class name (`IAuthor` ->
        # `i_author_id`), which doesn't match this table's plain `author_id` column
        return self.belongs_to(IAuthor, foreign_key="author_id")


class IComment(Model):
    __table_name__ = "e11_comments"
    __fields__: ClassVar = {"body": str, "author_id": int}
    __fillable__: ClassVar = ["body", "author_id"]
    __timestamps__ = False


class IRole(Model):
    __table_name__ = "e11_roles"
    __fields__: ClassVar = {"name": str}
    __fillable__: ClassVar = ["name"]
    __timestamps__ = False


_e11_author_role = sa.Table(
    "e11_author_role",
    sa.MetaData(),
    sa.Column("author_id", sa.Integer),
    sa.Column("role_id", sa.Integer),
    sa.Column("note", sa.String),
)


class CommentResource(JsonApiResource[IComment]):
    resource_type = "comments"


class AuthorResource(JsonApiResource[IAuthor]):
    resource_type = "authors"


class PostResource(JsonApiResource[IPost]):
    resource_type = "posts"
    relationships: ClassVar = {"author": AuthorResource}


AuthorResource.relationships = {"comments": CommentResource, "posts": PostResource}


async def _schema(db: ConnectionResolver) -> None:
    for model in (IAuthor, IPost, IComment, IRole):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    await db.execute(sa.schema.CreateTable(_e11_author_role))


async def _drop(db: ConnectionResolver) -> None:
    await db.execute(sa.schema.DropTable(_e11_author_role))
    for model in (IComment, IPost, IAuthor, IRole):
        await db.execute(sa.schema.DropTable(model.__table__))


def _client(kernel: HttpKernel) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=kernel.build())
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_nested_include_dedup_and_unknown_paths_on_postgres(postgres_url: str) -> None:
    db = ConnectionResolver({"default": {"url": postgres_url}})
    await _schema(db)
    try:
        author = await IAuthor.create(name="Ada")
        post = await IPost.create(title="Hello", author_id=author.id)
        await IComment.create(body="nice", author_id=author.id)
        await IComment.create(body="cool", author_id=author.id)

        async def handler(request: Any) -> Any:
            loaded = await IPost.with_("author.comments").where("id", post.id).first()
            return PostResource(loaded)

        kernel = HttpKernel()
        kernel.get("/nested", handler)
        async with _client(kernel) as client:
            # D2: ?include=author.comments -> both author and its comments in `included`
            resp = await client.get("/nested", params={"include": "author.comments"})
            assert resp.status_code == 200
            body = resp.json()
            types_ids = {(m["type"], m["id"]) for m in body["included"]}
            assert ("authors", str(author.id)) in types_ids
            assert len([t for t in types_ids if t[0] == "comments"]) == 2
            # to-many linkage: the author's `comments` relationship lists both comment ids
            author_member = next(m for m in body["included"] if m["type"] == "authors")
            assert {d["id"] for d in author_member["relationships"]["comments"]["data"]} == {
                str(c["id"]) for c in body["included"] if c["type"] == "comments"
            }

            # dedup across depth: author,author.comments -> author appears exactly once
            resp = await client.get("/nested", params={"include": "author,author.comments"})
            body = resp.json()
            authors = [m for m in body["included"] if m["type"] == "authors"]
            assert len(authors) == 1
            comments = [m for m in body["included"] if m["type"] == "comments"]
            assert len(comments) == 2
            keys = [(m["type"], m["id"]) for m in body["included"]]  # no dup anywhere
            assert len(keys) == len(set(keys))

            # unknown nested path ignored, not an error: author still included, no `unicorns`
            resp = await client.get("/nested", params={"include": "author.unicorns"})
            assert resp.status_code == 200
            body = resp.json()
            assert [m["type"] for m in body["included"]] == ["authors"]

            # first-level parity: ?include=author alone still yields exactly today's output
            resp = await client.get("/nested", params={"include": "author"})
            body = resp.json()
            assert [m["type"] for m in body["included"]] == ["authors"]
    finally:
        await _drop(db)
        await db.dispose()


async def test_ghost_relation_and_no_lazy_load_on_postgres(postgres_url: str) -> None:
    db = ConnectionResolver({"default": {"url": postgres_url}})
    await _schema(db)
    try:
        author = await IAuthor.create(name="Ada")
        post = await IPost.create(title="Hello", author_id=author.id)
        await IComment.create(body="nice", author_id=author.id)

        async def handler(request: Any) -> Any:
            loaded = await IPost.with_("author").where("id", post.id).first()
            return PostResource(loaded)

        kernel = HttpKernel()
        kernel.get("/ghost", handler)
        async with _client(kernel) as client:
            # ?include=ghost.comments -> no `ghost` relation declared/loaded -> empty included
            resp = await client.get("/ghost", params={"include": "ghost.comments"})
            assert resp.status_code == 200
            assert "included" not in resp.json()

            # no lazy load: author loaded, but its `comments` are NOT eager-loaded on author ->
            # author included, no comments, no exception, no DB query triggered
            resp = await client.get("/ghost", params={"include": "author.comments"})
            body = resp.json()
            assert [m["type"] for m in body["included"]] == ["authors"]
    finally:
        await _drop(db)
        await db.dispose()


class _CycleAuthorResource(JsonApiResource[IAuthor]):
    """A flat ``attributes()`` (not the default ``to_dict()``-derived one) — ``Model.to_dict()``
    itself walks nested loaded relations with no cycle guard of its own (a separate, pre-existing
    concern), which would recurse forever on this test's deliberately cyclic model graph before
    ``_collect_included``'s own guard ever got a chance to matter. Isolates the assertion to what
    D2 owns: the include-walker's cycle guard, not the model layer's relation-nesting depth."""

    resource_type = "authors"
    relationships: ClassVar = {}

    def to_array(self, request: Any | None = None) -> dict[str, Any]:
        return {"name": self.resource.name}


class _CyclePostResource(JsonApiResource[IPost]):
    resource_type = "posts"
    relationships: ClassVar = {"author": _CycleAuthorResource}

    def to_array(self, request: Any | None = None) -> dict[str, Any]:
        return {"title": self.resource.title}


_CycleAuthorResource.relationships = {"posts": _CyclePostResource}


async def test_cyclic_loaded_include_graph_terminates_on_postgres(postgres_url: str) -> None:
    db = ConnectionResolver({"default": {"url": postgres_url}})
    await _schema(db)
    try:
        author = await IAuthor.create(name="Ada")
        post = await IPost.create(title="Hello", author_id=author.id)

        # wire a cyclic *loaded* relation graph by hand: author.posts -> [post], post.author ->
        # the SAME author instance — a back-reference a real eager-load chain could produce
        # (author -> posts -> author -> posts -> ...).
        author._relations["posts"] = [post]
        post._relations["author"] = author

        resource = _CycleAuthorResource(author)
        # a deep dot-path that walks the cycle several times over — must return, not hang
        included = resource._collect_included(None, {"posts.author.posts.author.posts"}, set())
        keys = [(m["type"], m["id"]) for m in included]
        assert len(keys) == len(set(keys))  # deduplicated, and it returned at all
        assert ("posts", str(post.id)) in keys
        assert ("authors", str(author.id)) in keys
    finally:
        await _drop(db)
        await db.dispose()


class AuthorCountResource(JsonResource[IAuthor]):
    def to_array(self, request: Any | None = None) -> dict[str, Any]:
        return {"name": self.resource.name, "posts_count": self.when_counted("posts")}


async def test_when_counted_present_only_when_loaded_on_postgres(postgres_url: str) -> None:
    db = ConnectionResolver({"default": {"url": postgres_url}})
    await _schema(db)
    try:
        author = await IAuthor.create(name="Ada")
        await IPost.create(title="One", author_id=author.id)
        await IPost.create(title="Two", author_id=author.id)

        async def counted_handler(request: Any) -> Any:
            counted = (await IAuthor.with_count("posts").where("id", author.id).get())[0]
            return AuthorCountResource(counted)

        async def plain_handler(request: Any) -> Any:
            plain = await IAuthor.find(author.id)
            return AuthorCountResource(plain)

        kernel = HttpKernel()
        kernel.get("/counted", counted_handler)
        kernel.get("/plain", plain_handler)
        async with _client(kernel) as client:
            resp = await client.get("/counted")
            assert resp.json()["data"]["posts_count"] == 2

            resp = await client.get("/plain")
            assert "posts_count" not in resp.json()["data"]
    finally:
        await _drop(db)
        await db.dispose()


class RolePivotResource(JsonResource[IRole]):
    def to_array(self, request: Any | None = None) -> dict[str, Any]:
        return {"name": self.resource.name, "pivot": self.when_pivot_loaded()}


async def test_when_pivot_loaded_present_only_with_a_pivot_on_postgres(postgres_url: str) -> None:
    db = ConnectionResolver({"default": {"url": postgres_url}})
    await _schema(db)
    try:
        author = await IAuthor.create(name="Ada")
        role = await IRole.create(name="editor")
        await author.roles().attach(role.id, note="granted-by-admin")

        async def with_pivot_handler(request: Any) -> Any:
            fetched = (await author.roles().get())[0]
            return RolePivotResource(fetched)

        async def no_pivot_handler(request: Any) -> Any:
            bare_role = await IRole.find(role.id)
            return RolePivotResource(bare_role)

        kernel = HttpKernel()
        kernel.get("/with-pivot", with_pivot_handler)
        kernel.get("/no-pivot", no_pivot_handler)
        async with _client(kernel) as client:
            resp = await client.get("/with-pivot")
            assert resp.json()["data"]["pivot"] == {"note": "granted-by-admin"}

            resp = await client.get("/no-pivot")
            assert "pivot" not in resp.json()["data"]
    finally:
        await _drop(db)
        await db.dispose()
