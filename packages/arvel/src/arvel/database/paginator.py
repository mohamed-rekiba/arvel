"""Pagination result wrapper."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Generic, TypeVar
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

T = TypeVar("T")
S = TypeVar("S")


def build_page_url(base_url: str, page: int, *, query: Mapping[str, str] | None = None) -> str:
    """Compose a URL with ``page={page}`` merged into ``base_url``'s query string.

    ``query`` extras win over any pre-existing query params on ``base_url``
    except for ``page``, which the paginator always owns.
    """
    parts = urlsplit(base_url)
    params: dict[str, str] = dict(parse_qsl(parts.query, keep_blank_values=True))
    if query:
        params.update(query)
    # Paginator owns the page key — overwrite whatever the caller passed.
    params["page"] = str(page)
    encoded = urlencode(params)
    # Strip a trailing slash on the path so the URL reads cleanly: /posts?page=1
    # instead of /posts/?page=1. Preserves the empty-path case (just the host).
    path = parts.path.rstrip("/") if parts.path not in {"", "/"} else parts.path
    return urlunsplit((parts.scheme, parts.netloc, path, encoded, parts.fragment))


def build_cursor_url(base_url: str, cursor: str, *, query: Mapping[str, str] | None = None) -> str:
    """Compose a URL with ``cursor={cursor}`` merged into ``base_url``'s query.

    Cursor paginators own the ``cursor`` key. Any inbound ``cursor`` value
    on ``base_url`` or in ``query`` is overwritten with the paginator's
    next-page cursor.
    """
    parts = urlsplit(base_url)
    params: dict[str, str] = dict(parse_qsl(parts.query, keep_blank_values=True))
    if query:
        params.update(query)
    params["cursor"] = cursor
    encoded = urlencode(params)
    path = parts.path.rstrip("/") if parts.path not in {"", "/"} else parts.path
    return urlunsplit((parts.scheme, parts.netloc, path, encoded, parts.fragment))


@dataclass(frozen=True, slots=True)
class Paginator(Generic[T]):
    """Result of ``QueryBuilder.paginate(per_page)``.

    Attributes match the conventional Laravel paginator surface so an Eloquent
    developer knows where to look.
    """

    items: list[T]
    total: int
    per_page: int
    current_page: int

    @property
    def last_page(self) -> int:
        if self.total == 0:
            return 1
        return max(1, math.ceil(self.total / self.per_page))

    @property
    def has_more_pages(self) -> bool:
        return self.current_page < self.last_page

    def links(
        self,
        base_url: str,
        *,
        query: Mapping[str, str] | None = None,
    ) -> dict[str, str | None]:
        """Return the ``{first, prev, next, last}`` URL dict.

        ``base_url`` is the canonical resource URL (no ``page`` parameter).
        ``query`` is merged into every link so filters and sorts survive
        pagination.
        """
        last = self.last_page
        prev_page = self.current_page - 1 if self.current_page > 1 else None
        next_page = self.current_page + 1 if self.has_more_pages else None
        return {
            "first": build_page_url(base_url, 1, query=query),
            "prev": build_page_url(base_url, prev_page, query=query) if prev_page else None,
            "next": build_page_url(base_url, next_page, query=query) if next_page else None,
            "last": build_page_url(base_url, last, query=query),
        }

    def to_dict(
        self,
        items_serializer: Callable[[T], Any] | None = None,
        *,
        base_url: str | None = None,
        query: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """Return the paginator as a dict with ``data``, ``meta``, and ``links``.

        ``items_serializer`` is called on each item. Pass ``None`` to include
        items as-is (useful when items are already dicts).

        When ``base_url`` is ``None`` (the default), ``links`` values are
        integer page numbers — callers prepend the base URL themselves. Pass
        ``base_url`` to get fully-built URL strings (HATEOAS-style).
        """
        last = self.last_page
        from_ = (self.current_page - 1) * self.per_page + 1 if self.total > 0 else 0
        to = min(self.current_page * self.per_page, self.total)
        data: list[Any] = (
            [items_serializer(item) for item in self.items]
            if items_serializer is not None
            else list(self.items)
        )
        if base_url is not None:
            links: dict[str, Any] = self.links(base_url, query=query)
        else:
            links = {
                "first": 1,
                "prev": self.current_page - 1 if self.current_page > 1 else None,
                "next": self.current_page + 1 if self.has_more_pages else None,
                "last": last,
            }
        return {
            "data": data,
            "meta": {
                "total": self.total,
                "per_page": self.per_page,
                "current_page": self.current_page,
                "last_page": last,
                "from": from_,
                "to": to,
            },
            "links": links,
        }


__all__ = ["Paginator", "build_cursor_url", "build_page_url"]
