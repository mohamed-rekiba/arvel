"""arvel.cache.TaggedCache — the per-verb surface (has/forget/touch/expire/remember/pull) that
mirrors the untagged repository but scopes every key to its tag set. Array driver."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.cache import CacheManager


def _cache() -> Any:
    return CacheManager().driver()


async def test_tagged_verbs_scope_to_the_tag_set() -> None:
    tagged = _cache().tags("people")

    assert await tagged.has("k") is False
    await tagged.put("k", "v", ttl=60)
    assert await tagged.has("k") is True
    assert await tagged.pull("k") == "v"  # read-and-remove
    assert await tagged.has("k") is False

    await tagged.forever("f", "x")
    assert await tagged.forget("f") is True
    assert await tagged.has("f") is False


async def test_tagged_touch_and_expire() -> None:
    tagged = _cache().tags("t")
    await tagged.put("k", "v", ttl=60)
    assert await tagged.touch("k", 120) is True
    assert await tagged.expire("k", 5) is True


async def test_tagged_remember_and_remember_forever() -> None:
    tagged = _cache().tags("memo")
    calls: list[str] = []

    async def compute() -> str:
        calls.append("ran")
        return "computed"

    assert await tagged.remember("a", 60, compute) == "computed"
    assert await tagged.remember("a", 60, compute) == "computed"  # served from store
    assert calls == ["ran"]
    assert await tagged.remember_forever("b", compute) == "computed"


def test_tags_requires_at_least_one_name() -> None:
    with pytest.raises(ValueError, match="at least one tag name"):
        _cache().tags()


async def test_forget_prunes_the_tag_member() -> None:
    cache = _cache()
    tagged = cache.tags("users")
    await tagged.put("a", 1)
    await tagged.forget("a")
    # the member set no longer holds the forgotten entry (no dead-member leak)
    leftover = list(await cache.client.set_pop(tagged._tagset_key("users"), 100))  # pyright: ignore[reportPrivateUsage]
    assert leftover == []


async def test_prune_reclaims_dead_tag_members() -> None:
    cache = _cache()
    tagged = cache.tags("orders")
    await tagged.put("live", "v1")
    await tagged.put("gone", "v2")
    # simulate a TTL-expired entry: drop the value at the repository level, orphaning its member
    await cache.forget(tagged._scoped_key("gone"))  # pyright: ignore[reportPrivateUsage]

    assert await tagged.prune() == 1  # the orphaned "gone" member was reclaimed
    assert await tagged.get("live") == "v1"  # the live entry is untouched
    assert await tagged.prune() == 0  # nothing dead left
