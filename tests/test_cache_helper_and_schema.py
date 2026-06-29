"""Helpers (doc 06/10) — global cache() helper + arvel.Schema native wrapper."""

from __future__ import annotations

from arvel import Schema, validate
from arvel.support import cache


async def test_cache_helper_returns_default_driver() -> None:
    # cache() resolves the container-bound CacheManager; support is a leaf and no longer
    # constructs one app-less (DR-0026). Boot a minimal app with the cache provider.
    from arvel.cache.provider import CacheServiceProvider
    from arvel.kernel import Application, set_application

    app = Application()
    CacheServiceProvider(app).register()
    set_application(app)
    try:
        c = cache()
        await c.put("greeting", "hi", ttl=60)
        assert await c.get("greeting") == "hi"
        assert await c.get("missing", default="x") == "x"
    finally:
        set_application(None)


def test_cache_helper_requires_application() -> None:
    from arvel.kernel import set_application

    set_application(None)
    try:
        cache()
    except RuntimeError as exc:
        assert "requires a booted application" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("cache() must raise without a booted app")


def test_schema_is_native_validation_base() -> None:
    class CreatePost(Schema):
        title: str
        published: bool = False

    post = validate({"title": "Hello", "published": "true"}, CreatePost)
    assert post.title == "Hello"
    assert post.published is True  # coerced
