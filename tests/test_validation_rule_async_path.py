"""Custom Rule objects with async I/O are awaited on the async validation path (G11).

A rule that overrides ``passes_async`` runs on ``Validator.passes_async``/``fails_async`` (and the
async FormRequest path); a plain sync ``Rule`` still works there via the default delegation.
"""

from __future__ import annotations

from typing import Any

from arvel.validation import Rule, Validator


class AsyncTaken(Rule):
    message = "The :attribute is already taken."

    async def passes_async(self, attribute: str, value: Any) -> bool:
        import asyncio

        await asyncio.sleep(0)  # genuinely async — a stand-in for a lookup/API call
        return value != "taken"

    def passes(self, attribute: str, value: Any) -> bool:
        return True  # the sync path can't run the async check; the real check is passes_async


class SyncUpper(Rule):
    message = "The :attribute must be uppercase."

    def passes(self, attribute: str, value: Any) -> bool:
        return str(value).isupper()


async def test_custom_async_rule_is_awaited_and_can_fail() -> None:
    v = Validator({"name": "taken"}, {"name": [AsyncTaken()]})
    assert await v.fails_async() is True
    assert "name" in v.errors()


async def test_custom_async_rule_passes_when_valid() -> None:
    v = Validator({"name": "free"}, {"name": [AsyncTaken()]})
    assert await v.passes_async() is True


async def test_plain_sync_rule_still_runs_on_the_async_path() -> None:
    assert await Validator({"code": "abc"}, {"code": [SyncUpper()]}).fails_async() is True
    assert await Validator({"code": "ABC"}, {"code": [SyncUpper()]}).passes_async() is True
