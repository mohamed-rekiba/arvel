"""Spec 12 §2 — `Enum` rule object (Laravel `Rule::enum()`). No string form: the enum class IS the
closed set, so it's a `Rule` object (runs on the async path, like any custom rule)."""

from __future__ import annotations

import enum

from arvel.validation import Enum, Validator


class Status(enum.Enum):
    ACTIVE = "active"
    CLOSED = "closed"


async def test_enum_rule_passes_for_a_member_value() -> None:
    v = Validator({"status": "active"}, {"status": [Enum(Status)]})
    assert await v.passes_async()


async def test_enum_rule_fails_for_a_non_member_value() -> None:
    v = Validator({"status": "bogus"}, {"status": [Enum(Status)]})
    assert await v.fails_async()
    assert "Status" in v.errors()["status"][0]


async def test_enum_rule_mixes_with_string_rules() -> None:
    v = Validator({"status": "active"}, {"status": ["required", Enum(Status)]})
    assert await v.passes_async()
