"""Meilisearch filter values encode as engine literals, not Python repr (round H12)."""

from __future__ import annotations

from arvel.search import _filter_value


def test_bool_and_none_use_engine_literals() -> None:
    assert _filter_value(True) == "true"
    assert _filter_value(False) == "false"
    assert _filter_value(None) == "null"


def test_numbers_and_strings() -> None:
    assert _filter_value(5) == "5"
    assert _filter_value(3.5) == "3.5"
    assert _filter_value("active") == "'active'"  # quoted string literal
