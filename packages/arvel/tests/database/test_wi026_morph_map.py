"""WI-arvel-026 — Epic 007 Story 1: morph map foundation.

- `get_morph_class()` returns the short class name by default, the alias when mapped.
- `morph_map({...})` registers/returns aliases; `merge=False` replaces.
- `require_morph_map()` makes an unmapped polymorphic model raise.
- `resolve_morph_class(alias)` goes token -> class (map first, registry fallback).
- A row written through a morph accessor stores the alias in `{name}_type`.
"""

from __future__ import annotations

from typing import ClassVar

import pytest
from arvel.database import Model, morph_map, require_morph_map
from arvel.database.orm import MorphMapError, MorphOne, get_morph_alias, resolve_morph_class
from sqlalchemy import Integer, String
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column


class Wi026Image(Model):
    __tablename__ = "wi026_images"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    url: Mapped[str] = mapped_column(String(200), nullable=False)
    imageable_type: Mapped[str] = mapped_column(String(60), nullable=False)
    imageable_id: Mapped[int] = mapped_column(Integer, nullable=False)


class Wi026Post(Model):
    __tablename__ = "wi026_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    title: Mapped[str] = mapped_column(String(120), nullable=False)

    image: ClassVar[MorphOne[Wi026Image]] = MorphOne(Wi026Image, name="imageable")


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


class TestGetMorphClass:
    def test_default_is_short_name(self) -> None:
        assert Wi026Post.get_morph_class() == "Wi026Post"

    def test_alias_when_mapped(self) -> None:
        morph_map({"post": Wi026Post})
        assert Wi026Post.get_morph_class() == "post"
        assert get_morph_alias(Wi026Post) == "post"


class TestMorphMapRegistry:
    def test_returns_current_map(self) -> None:
        morph_map({"post": Wi026Post})
        assert morph_map() == {"post": Wi026Post}

    def test_merge_extends(self) -> None:
        morph_map({"post": Wi026Post})
        morph_map({"image": Wi026Image})
        assert morph_map() == {"post": Wi026Post, "image": Wi026Image}

    def test_no_merge_replaces(self) -> None:
        morph_map({"post": Wi026Post})
        morph_map({"image": Wi026Image}, merge=False)
        assert morph_map() == {"image": Wi026Image}


class TestRequireMorphMap:
    def test_unmapped_raises(self) -> None:
        require_morph_map(True)
        with pytest.raises(MorphMapError, match="Wi026Post"):
            Wi026Post.get_morph_class()

    def test_mapped_passes_in_strict_mode(self) -> None:
        morph_map({"post": Wi026Post})
        require_morph_map(True)
        assert Wi026Post.get_morph_class() == "post"


class TestResolveMorphClass:
    def test_via_map(self) -> None:
        morph_map({"post": Wi026Post})
        assert resolve_morph_class("post") is Wi026Post

    def test_fallback_by_short_name(self) -> None:
        assert resolve_morph_class("Wi026Post") is Wi026Post

    def test_unknown_raises(self) -> None:
        with pytest.raises(MorphMapError, match="nope"):
            resolve_morph_class("nope")


class TestWrittenTokenUsesAlias:
    async def test_create_stores_alias(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        morph_map({"post": Wi026Post})
        post = await Wi026Post.create(title="Hello")
        img = await post.image.create(url="/a.png")
        assert img.imageable_type == "post"

    async def test_create_stores_short_name_without_map(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        post = await Wi026Post.create(title="Hello")
        img = await post.image.create(url="/a.png")
        assert img.imageable_type == "Wi026Post"
        # And the accessor reads it back through the same token.
        assert (await post.image) is not None
