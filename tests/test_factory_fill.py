"""Factory fill (2.8): callable sequences (receive the 0-based iteration index, dict cycling
preserved) and the `trashed()` state helper for SoftDeletes models."""

from __future__ import annotations

from typing import Any, ClassVar

import pytest
import sqlalchemy as sa

from arvel import Model
from arvel.database import ConnectionResolver, Factory, SoftDeletes


class Widget(Model):
    __table_name__ = "factory_fill_widgets"
    __fields__: ClassVar[dict[str, Any]] = {"name": str, "price": int}
    __fillable__: ClassVar[list[str]] = ["name", "price"]


class WidgetFactory(Factory[Widget]):
    model = Widget

    def definition(self) -> dict[str, Any]:
        return {"name": "widget", "price": 10}


class Post(Model, SoftDeletes):
    __table_name__ = "factory_fill_posts"
    __fields__: ClassVar[dict[str, Any]] = {"title": str}
    __fillable__: ClassVar[list[str]] = ["title"]


class PostFactory(Factory[Post]):
    model = Post

    def definition(self) -> dict[str, Any]:
        return {"title": "a post"}


def test_callable_sequence_receives_the_iteration_index() -> None:
    made = WidgetFactory().count(4).sequence(lambda i: {"price": i * 10}).make()
    assert [w.price for w in made] == [0, 10, 20, 30]


def test_dict_sequence_still_cycles() -> None:
    """Pre-existing dict-sequence cycling behavior is untouched by adding callable support."""
    made = WidgetFactory().count(3).sequence({"price": 1}, {"price": 2}).make()
    assert [w.price for w in made] == [1, 2, 1]


def test_mixed_dict_and_callable_sequence_items() -> None:
    made = (
        WidgetFactory().count(4).sequence({"name": "fixed"}, lambda i: {"name": f"seq-{i}"}).make()
    )
    # item cycles by index % 2: index 0,2 -> dict; index 1,3 -> callable(index)
    assert [w.name for w in made] == ["fixed", "seq-1", "fixed", "seq-3"]


async def test_trashed_sets_deleted_at_for_soft_delete_model() -> None:
    db = ConnectionResolver()
    Post.set_connection(db)
    await db.execute(sa.schema.CreateTable(Post.__table__))
    try:
        post = await PostFactory().trashed().create()
        assert post.trashed() is True
        assert post._attributes["deleted_at"] is not None
    finally:
        await db.dispose()


def test_trashed_raises_for_non_soft_delete_model() -> None:
    with pytest.raises(TypeError, match="SoftDeletes"):
        WidgetFactory().trashed()
