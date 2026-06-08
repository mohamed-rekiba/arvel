"""WI-arvel-005 — ``when_loaded`` must surface Arvel's eager-relation cache.

The mock-based parity tests only exercised the ``__dict__`` path. Async relations
(``with_("tags")``) cache results under ``__arvel_eager_relations__``, so this uses a
real ``MorphToMany`` model to pin the documented eager-load → serialize contract.
"""

from __future__ import annotations

from typing import Any, ClassVar

from arvel.database import Model, id_, string
from arvel.database.orm import MorphToMany
from arvel.http.resources import JsonResource
from sqlalchemy import Column, ForeignKey, Integer, String, Table
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

wi005_taggables = Table(
    "wi005_taggables",
    Model.metadata,
    Column("tag_id", Integer, ForeignKey("wi005_tags.id"), primary_key=True),
    Column("taggable_type", String(255), primary_key=True),
    Column("taggable_id", String(64), primary_key=True),
)


class Wi005Tag(Model):
    __tablename__ = "wi005_tags"
    id: int = id_()
    name: str = string(80)


class Wi005Post(Model):
    __tablename__ = "wi005_posts"
    id: int = id_()
    title: str = string(80)
    tags: ClassVar[MorphToMany[Wi005Tag]] = MorphToMany(
        Wi005Tag, table=wi005_taggables, name="taggable", related_key="tag_id"
    )


class Wi005PostResource(JsonResource[Wi005Post]):
    def to_dict(self, request: Any) -> dict[str, Any]:
        return {"title": self.resource.title, "tags": self.when_loaded("tags")}


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


async def test_when_loaded_returns_eager_pivot(engine: AsyncEngine, session: AsyncSession) -> None:
    await _setup(engine)
    post = await Wi005Post.create(title="p")
    red = await Wi005Tag.create(name="red")
    blue = await Wi005Tag.create(name="blue")
    await post.tags.attach(red.id)
    await post.tags.attach(blue.id)

    loaded = (await Wi005Post.query().with_("tags").all())[0]
    body = Wi005PostResource(loaded).to_dict(None)

    assert "tags" in body
    assert sorted(t.name for t in body["tags"]) == ["blue", "red"]


async def test_when_loaded_absent_without_eager_load(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _setup(engine)
    post = await Wi005Post.create(title="p")
    await post.tags.attach((await Wi005Tag.create(name="red")).id)

    # No with_("tags") → relation not hydrated → key stripped, no lazy load.
    fresh = await Wi005Post.query().where(Wi005Post.id == post.id).first()
    assert fresh is not None
    body = Wi005PostResource(fresh).to_dict(None)
    assert "tags" not in body


async def test_when_loaded_committed_dict_relation() -> None:
    """The existing ``__dict__`` path still resolves (no regression)."""

    class _Plain:
        def __init__(self) -> None:
            self.posts = ["a", "b"]

    class _Res(JsonResource["_Plain"]):
        def to_dict(self, request: Any) -> dict[str, Any]:
            return {"posts": self.when_loaded("posts")}

    assert _Res(_Plain()).to_dict(None) == {"posts": ["a", "b"]}
