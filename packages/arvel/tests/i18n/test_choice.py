"""Tests for __choice() pluralisation — FR-015-027, FR-015-028."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

import pytest


class _ParseChoice(Protocol):
    def __call__(self, spec: str, *, count: int, replace: Mapping[str, object]) -> str: ...


@pytest.fixture
def parse_choice() -> _ParseChoice:
    from arvel.i18n.pluralisation import select_plural_variant

    return select_plural_variant


class TestLaravelPipeSimple:
    """FR-015-027 — `'a|b|c'` positional ordering."""

    @pytest.mark.parametrize(
        ("count", "expected"),
        [(0, "no items"), (1, "one item"), (5, "many items")],
    )
    def test_three_variant_pipe(
        self, parse_choice: _ParseChoice, count: int, expected: str
    ) -> None:
        spec = "no items|one item|many items"
        out = parse_choice(spec, count=count, replace={})
        assert out == expected


class TestPlaceholder:
    """count substitution into :count or {count}."""

    def test_substitutes_count_placeholder(self, parse_choice: _ParseChoice) -> None:
        spec = "no items|one item|:count items"
        assert parse_choice(spec, count=5, replace={"count": 5}) == "5 items"


class TestBracketRanges:
    """FR-015-028 — `{0}` exact, `[1,4]` range."""

    @pytest.mark.parametrize(
        ("count", "expected"),
        [
            (0, "none"),
            (1, "few"),
            (2, "few"),
            (4, "few"),
            (5, "other"),
            (100, "other"),
        ],
    )
    def test_bracket_range_syntax(
        self, parse_choice: _ParseChoice, count: int, expected: str
    ) -> None:
        spec = "{0}none|[1,4]few|other"
        assert parse_choice(spec, count=count, replace={}) == expected

    def test_open_ended_range(self, parse_choice: _ParseChoice) -> None:
        spec = "{0}none|[1,*]many"
        assert parse_choice(spec, count=999, replace={}) == "many"
