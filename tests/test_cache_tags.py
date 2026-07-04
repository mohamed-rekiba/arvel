"""Cache (spec 06-cache-parity §3) — tags: entries are readable only through the same tags, and
`flush()` on a tag removes only its own entries (array driver, in-memory tag index)."""

from __future__ import annotations

from typing import Any

from arvel.cache import CacheManager


def _cache() -> Any:
    return CacheManager().driver()


async def test_tagged_entry_readable_only_through_the_same_tags() -> None:
    cache = _cache()
    await cache.tags("people").put("k", "tagged-value")
    assert await cache.tags("people").get("k") == "tagged-value"
    # not visible untagged, nor via a different tag
    assert await cache.get("k") is None
    assert await cache.tags("other").get("k") is None


async def test_tag_order_is_irrelevant_same_scope() -> None:
    cache = _cache()
    await cache.tags("a", "b").put("k", "v")
    assert await cache.tags("b", "a").get("k") == "v"


async def test_flush_removes_only_the_tagged_entries() -> None:
    cache = _cache()
    await cache.tags("a").put("k1", "v1")
    await cache.tags("b").put("k2", "v2")
    await cache.put("k3", "v3")  # untagged, unrelated

    assert await cache.tags("a").flush() is True

    assert await cache.tags("a").get("k1") is None  # gone
    assert await cache.tags("b").get("k2") == "v2"  # unaffected
    assert await cache.get("k3") == "v3"  # unaffected


async def test_flush_invalidates_across_combinations_sharing_the_tag() -> None:
    """Flushing tag `a` alone also invalidates entries written via a combination that includes it
    (Laravel's cross-combination tag invalidation)."""
    cache = _cache()
    await cache.tags("a", "b").put("combo", "v")
    assert await cache.tags("a", "b").get("combo") == "v"

    await cache.tags("a").flush()

    assert await cache.tags("a", "b").get("combo") is None


async def test_tagged_verbs_add_pull_forever_increment() -> None:
    cache = _cache()
    tagged = cache.tags("counters")

    assert await tagged.add("k", "v") is True
    assert await tagged.add("k", "other") is False

    assert await tagged.forever("forever-k", "persisted") is True
    assert await tagged.get("forever-k") == "persisted"

    assert await tagged.increment("n", 5) == 5
    assert await tagged.decrement("n", 2) == 3

    assert await tagged.pull("k") == "v"
    assert await tagged.get("k") is None
