"""Pagination result wrapper."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from contextvars import ContextVar, Token
from dataclasses import dataclass, field, replace
from typing import Any, Generic, TypeVar
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

T = TypeVar("T")
S = TypeVar("S")


def _empty_query() -> dict[str, str]:
    return {}


@dataclass(frozen=True, slots=True)
class PaginationRequest:
    """The current request's path and query string, set by the HTTP middleware.

    Lets paginators resolve the active page/cursor and rebuild URLs without the
    database layer importing anything HTTP-specific.
    """

    path: str
    query: Mapping[str, str]


_pagination_request: ContextVar[PaginationRequest | None] = ContextVar(
    "_arvel_pagination_request", default=None
)


def set_pagination_request(req: PaginationRequest) -> Token[PaginationRequest | None]:
    return _pagination_request.set(req)


def get_pagination_request() -> PaginationRequest | None:
    return _pagination_request.get()


def reset_pagination_request(token: Token[PaginationRequest | None]) -> None:
    _pagination_request.reset(token)


def resolve_page(page_name: str = "page", default: int = 1) -> int:
    """Read the current page from the request query (``?page=N``), clamped to ``>= 1``."""
    req = _pagination_request.get()
    if req is None:
        return default
    raw = req.query.get(page_name)
    if raw is None:
        return default
    try:
        page = int(raw)
    except TypeError, ValueError:
        return default
    return page if page >= 1 else default


def resolve_cursor(cursor_name: str = "cursor") -> str | None:
    """Read the opaque cursor token from the request query (``?cursor=...``)."""
    req = _pagination_request.get()
    return req.query.get(cursor_name) if req is not None else None


def resolve_path(explicit: str | None = None) -> str:
    """Pick the URL path for link building: explicit wins, then the request, then ``/``."""
    if explicit is not None:
        return explicit
    req = _pagination_request.get()
    return req.path if req is not None else "/"


def _page_window(current: int, last: int, on_each_side: int) -> list[int | None]:
    """Windowed page numbers around ``current``; ``None`` marks an elided gap."""
    if last <= 1:
        return [1] if last == 1 else []
    threshold = on_each_side * 2 + 6
    if last <= threshold:
        return list(range(1, last + 1))
    pages: list[int | None] = [1]
    start = max(2, current - on_each_side)
    end = min(last - 1, current + on_each_side)
    if start > 2:
        pages.append(None)
    pages.extend(range(start, end + 1))
    if end < last - 1:
        pages.append(None)
    pages.append(last)
    return pages


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
    page_name: str = "page"
    path: str | None = None
    on_each_side: int = 3
    appended: Mapping[str, str] = field(default_factory=_empty_query)
    fragment_: str | None = None

    @property
    def last_page(self) -> int:
        if self.total == 0:
            return 1
        return max(1, math.ceil(self.total / self.per_page))

    def appends(self, values: Mapping[str, str]) -> Paginator[T]:
        """Add query params that every generated URL should carry."""
        return replace(self, appended={**dict(self.appended), **dict(values)})

    def with_query_string(self) -> Paginator[T]:
        """Carry the current request's query params (except the page key) onto every URL."""
        req = get_pagination_request()
        if req is None:
            return self
        merged = {k: v for k, v in req.query.items() if k != self.page_name}
        return replace(self, appended={**merged, **dict(self.appended)})

    def fragment(self, value: str | None) -> Paginator[T]:
        """Append ``#value`` to every generated URL."""
        return replace(self, fragment_=value)

    def _url_for_page(self, page: int) -> str:
        base = resolve_path(self.path)
        if self.fragment_:
            base = f"{base}#{self.fragment_}"
        return build_page_url(base, page, query=self.appended or None)

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

    def _link_collection(self) -> list[dict[str, Any]]:
        last = self.last_page
        prev_url = self._url_for_page(self.current_page - 1) if self.current_page > 1 else None
        next_url = self._url_for_page(self.current_page + 1) if self.has_more_pages else None
        elements: list[dict[str, Any]] = [
            {"url": prev_url, "label": "&laquo; Previous", "active": False}
        ]
        for page in _page_window(self.current_page, last, self.on_each_side):
            if page is None:
                elements.append({"url": None, "label": "...", "active": False})
            else:
                elements.append(
                    {
                        "url": self._url_for_page(page),
                        "label": str(page),
                        "active": page == self.current_page,
                    }
                )
        elements.append({"url": next_url, "label": "Next &raquo;", "active": False})
        return elements

    def to_response(self, items_serializer: Callable[[T], Any] | None = None) -> dict[str, Any]:
        """Laravel's flat ``LengthAwarePaginator`` envelope (``current_page`` … ``total``).

        URLs honor ``appends``/``with_query_string``/``fragment`` and the request path. The
        ``links`` array is the windowed page list (controlled by ``on_each_side``) with the
        ``&laquo; Previous`` / ``Next &raquo;`` bookends — drop-in for Laravel API clients.
        """
        last = self.last_page
        from_ = (self.current_page - 1) * self.per_page + 1 if self.total > 0 else None
        to = min(self.current_page * self.per_page, self.total) if self.total > 0 else None
        data: list[Any] = (
            [items_serializer(item) for item in self.items]
            if items_serializer is not None
            else list(self.items)
        )
        return {
            "current_page": self.current_page,
            "data": data,
            "first_page_url": self._url_for_page(1),
            "from": from_,
            "last_page": last,
            "last_page_url": self._url_for_page(last),
            "links": self._link_collection(),
            "next_page_url": (
                self._url_for_page(self.current_page + 1) if self.has_more_pages else None
            ),
            "path": resolve_path(self.path),
            "per_page": self.per_page,
            "prev_page_url": (
                self._url_for_page(self.current_page - 1) if self.current_page > 1 else None
            ),
            "to": to,
            "total": self.total,
        }


__all__ = [
    "PaginationRequest",
    "Paginator",
    "build_cursor_url",
    "build_page_url",
    "get_pagination_request",
    "reset_pagination_request",
    "resolve_cursor",
    "resolve_page",
    "resolve_path",
    "set_pagination_request",
]
