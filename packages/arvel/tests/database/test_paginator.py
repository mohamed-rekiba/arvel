"""Paginator math."""

from __future__ import annotations

from arvel.database.paginator import Paginator


def test_paginator_last_page_when_empty() -> None:
    p: Paginator[int] = Paginator(items=[], total=0, per_page=10, current_page=1)
    assert p.last_page == 1
    assert p.has_more_pages is False


def test_paginator_last_page_round_up() -> None:
    p: Paginator[int] = Paginator(items=[1] * 10, total=23, per_page=10, current_page=1)
    assert p.last_page == 3
    assert p.has_more_pages is True


def test_paginator_last_page_when_at_last() -> None:
    p: Paginator[int] = Paginator(items=[1] * 3, total=23, per_page=10, current_page=3)
    assert p.last_page == 3
    assert p.has_more_pages is False
