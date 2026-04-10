"""Pagination primitives — offset-based and cursor-based result containers.

``PaginatedResult`` and ``CursorResult`` are generic dataclasses that hold
query results with pagination metadata. Both provide:

- ``to_response()`` → typed ``TypedDict`` for API serialization
"""

from __future__ import annotations

import base64
import math
from dataclasses import dataclass
from typing import Any, TypedDict

MAX_PER_PAGE: int = 100


class PaginationMeta(TypedDict):
    """Typed metadata for offset-based pagination."""

    total: int
    page: int
    per_page: int
    last_page: int
    has_more: bool


class PaginatedResponse(TypedDict):
    """Typed response for offset-based pagination, suitable for API serialization."""

    data: list[Any]
    meta: PaginationMeta


class CursorMeta(TypedDict):
    """Typed metadata for cursor-based pagination."""

    next_cursor: str | None
    has_more: bool


class CursorResponse(TypedDict):
    """Typed response for cursor-based pagination, suitable for API serialization."""

    data: list[Any]
    meta: CursorMeta


@dataclass(frozen=True)
class PaginatedResult[T]:
    """Offset-based pagination result."""

    data: list[T]
    total: int
    page: int
    per_page: int

    def __post_init__(self) -> None:
        if self.per_page > MAX_PER_PAGE:
            object.__setattr__(self, "per_page", MAX_PER_PAGE)

    @property
    def last_page(self) -> int:
        if self.total == 0:
            return 0
        return math.ceil(self.total / self.per_page)

    @property
    def has_more(self) -> bool:
        return self.page < self.last_page

    def to_response(self) -> PaginatedResponse:
        """Return a typed response dict for API serialization."""
        return PaginatedResponse(
            data=self.data,
            meta=PaginationMeta(
                total=self.total,
                page=self.page,
                per_page=self.per_page,
                last_page=self.last_page,
                has_more=self.has_more,
            ),
        )


@dataclass(frozen=True)
class CursorResult[T]:
    """Cursor-based pagination result."""

    data: list[T]
    next_cursor: str | None
    has_more: bool

    def to_response(self) -> CursorResponse:
        """Return a typed response dict for API serialization."""
        return CursorResponse(
            data=self.data,
            meta=CursorMeta(
                next_cursor=self.next_cursor,
                has_more=self.has_more,
            ),
        )


def encode_cursor(field: str, value: Any) -> str:
    """Encode a cursor value as an opaque base64 string."""
    raw = f"{field}:{value}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[str, str]:
    """Decode an opaque cursor back to (field, value)."""
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    field, _, value = raw.partition(":")
    return field, value
