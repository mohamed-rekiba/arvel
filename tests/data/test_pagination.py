"""Tests for pagination — Story 5 + Epic 13c Story 6."""

from __future__ import annotations

import base64

from arvel.data.pagination import (
    MAX_PER_PAGE,
    CursorResult,
    PaginatedResult,
    decode_cursor,
    encode_cursor,
)


class TestPaginatedResult:
    def test_last_page_calculation(self) -> None:
        result = PaginatedResult(
            data=list(range(20)),
            total=95,
            page=1,
            per_page=20,
        )
        assert result.last_page == 5

    def test_last_page_exact_division(self) -> None:
        result = PaginatedResult(data=[], total=100, page=1, per_page=20)
        assert result.last_page == 5

    def test_last_page_zero_total(self) -> None:
        result = PaginatedResult(data=[], total=0, page=1, per_page=20)
        assert result.last_page == 0

    def test_has_more_true(self) -> None:
        result = PaginatedResult(data=list(range(20)), total=95, page=1, per_page=20)
        assert result.has_more is True

    def test_has_more_false_on_last_page(self) -> None:
        result = PaginatedResult(data=list(range(15)), total=95, page=5, per_page=20)
        assert result.has_more is False

    def test_to_response_returns_typed_dict(self) -> None:
        result = PaginatedResult(data=[1, 2], total=10, page=1, per_page=2)
        resp = result.to_response()
        assert resp["data"] == [1, 2]
        assert resp["meta"]["total"] == 10
        assert resp["meta"]["page"] == 1
        assert resp["meta"]["per_page"] == 2
        assert resp["meta"]["last_page"] == 5
        assert resp["meta"]["has_more"] is True

    def test_per_page_capped_at_max(self) -> None:
        result = PaginatedResult(data=[], total=0, page=1, per_page=500)
        assert result.per_page == MAX_PER_PAGE

    def test_per_page_within_limit_unchanged(self) -> None:
        result = PaginatedResult(data=[], total=0, page=1, per_page=50)
        assert result.per_page == 50


class TestCursorResult:
    def test_basic(self) -> None:
        cursor = base64.b64encode(b"id:100").decode()
        result = CursorResult(data=[1, 2, 3], next_cursor=cursor, has_more=True)
        assert result.has_more is True
        assert result.next_cursor is not None

    def test_no_more(self) -> None:
        result = CursorResult(data=[1], next_cursor=None, has_more=False)
        assert result.has_more is False
        assert result.next_cursor is None

    def test_to_response_returns_typed_dict(self) -> None:
        result = CursorResult(data=[1], next_cursor="abc", has_more=True)
        resp = result.to_response()
        assert resp["data"] == [1]
        assert resp["meta"]["next_cursor"] == "abc"
        assert resp["meta"]["has_more"] is True

    def test_to_response_with_none_cursor(self) -> None:
        result = CursorResult(data=[], next_cursor=None, has_more=False)
        resp = result.to_response()
        assert resp["meta"]["next_cursor"] is None
        assert resp["meta"]["has_more"] is False


class TestCursorEncoding:
    def test_encode_decode_roundtrip(self) -> None:
        cursor = encode_cursor("id", 42)
        field, value = decode_cursor(cursor)
        assert field == "id"
        assert value == "42"

    def test_encode_is_opaque(self) -> None:
        cursor = encode_cursor("id", 100)
        assert "id" not in cursor
        assert "100" not in cursor
