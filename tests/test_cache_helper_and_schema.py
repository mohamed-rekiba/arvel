"""Helpers (doc 06/10) — global cache() helper + arvel.Schema native wrapper."""

from __future__ import annotations

from arvel import Schema, validate
from arvel.support import cache


async def test_cache_helper_returns_default_driver() -> None:
    c = cache()
    await c.put("greeting", "hi", ttl=60)
    assert await c.get("greeting") == "hi"
    assert await c.get("missing", default="x") == "x"


def test_schema_is_native_validation_base() -> None:
    class CreatePost(Schema):
        title: str
        published: bool = False

    post = validate({"title": "Hello", "published": "true"}, CreatePost)
    assert post.title == "Hello"
    assert post.published is True  # coerced
