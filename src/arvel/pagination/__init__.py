"""arvel.pagination — parity paginators.

``Builder.paginate()`` returns a:class:`LengthAwarePaginator` (knows the grand
``total`` → can render a full page-number list) and ``simple_paginate()`` returns a
:class:`Paginator` (a lean prev/next pager that only fetches one extra row to know
whether a *next* page exists). Both are **iterable** over their page of items, carry
the accessor surface (``total``/``current_page``/``last_page``/…), serialize
to the JSON shape via:meth:`to_dict`, and render an HTML page-link bar via
:meth:`links` (a shipped Jinja template under the ``pagination`` view namespace).

URL + current-page awareness mirrors the resolver pattern: the current request
path and ``?page=`` are resolved lazily from the bound request (``current_request``),
so a handler can simply ``await Post.paginate()`` and get correctly-linked pages.
Outside a request the paginator degrades safely (path ``"/"``, page ``1``).


"""

from __future__ import annotations

import base64
import json as _json
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

if TYPE_CHECKING:
    from collections.abc import Iterator

    from arvel.support import Collection

# --- injected dependencies (DR-0026) -----------------------------------------------
# pagination sits below http/views in the layered DAG and can't import them; those layers
# inject their resolver/renderer on import instead. Unset -> degrade (no request, page 1).
_request_resolver: Callable[[], Any] | None = None
_view_renderer: Callable[[str, dict[str, Any]], Awaitable[Any]] | None = None


def set_request_resolver(resolver: Callable[[], Any] | None) -> None:
    """Register the source of the current request (the http layer wires this)."""
    global _request_resolver
    _request_resolver = resolver


def set_view_renderer(renderer: Callable[[str, dict[str, Any]], Awaitable[Any]] | None) -> None:
    """Register the page-link-bar renderer (the views layer wires this)."""
    global _view_renderer
    _view_renderer = renderer


# --- per-request resolution ----------


def resolve_current_page(page_name: str = "page", default: int = 1) -> int:
    """The current page from the bound request's ``?<page_name>=`` (>= 1), else ``default``.

    Degrades to ``default`` outside a request or on a non-positive/non-numeric value —
    clamps a bad ``page`` to 1 rather than erroring."""
    raw = _request_query(page_name)
    if raw is None:
        return default
    try:
        page = int(raw)
    except TypeError, ValueError:
        return default
    return page if page >= 1 else default


def resolve_current_path(default: str = "/") -> str:
    """The bound request's path (no query string), else ``default`` outside a request."""
    request = _current_request()
    if request is None:
        return default
    try:
        return request.path() or default
    except Exception:  # pragma: no cover - defensive: a degenerate request object
        return default


def _current_request() -> Any:
    return _request_resolver() if _request_resolver is not None else None


def _request_query(key: str) -> Any:
    request = _current_request()
    if request is None:
        return None
    try:
        return request.query(key)
    except Exception:  # pragma: no cover - defensive
        return None


def _request_query_string(exclude: str) -> dict[str, Any]:
    """All current query params except ``exclude`` (the page key) — for ``with_query_string``."""
    request = _current_request()
    if request is None:
        return {}
    params = getattr(getattr(request, "raw", None), "query_params", None)
    if params is None:
        return {}
    try:
        return {k: v for k, v in params.items() if k != exclude}
    except Exception:  # pragma: no cover - defensive
        return {}


def _serialize(item: Any) -> Any:
    """``toArray`` parity for a page item: models → ``to_dict()``, else pass through."""
    to_dict = getattr(item, "to_dict", None)
    return to_dict() if callable(to_dict) else item


# --- base ---------------------------------------------------------------------------


class AbstractPaginator:
    """Shared paginator behavior: items, URL building, request-aware links + render."""

    def __init__(
        self,
        items: list[Any],
        per_page: int,
        current_page: int | None,
        *,
        path: str | None = None,
        query: dict[str, Any] | None = None,
        fragment: str | None = None,
        page_name: str = "page",
    ) -> None:
        self._items = list(items)
        self._per_page = max(1, per_page)  # guard div-by-zero in last_page
        self._page_name = page_name
        self._current_page = (
            current_page if current_page is not None else resolve_current_page(page_name)
        )
        self._path = (path if path is not None else resolve_current_path()).rstrip("/") or "/"
        self._query: dict[str, Any] = dict(query) if query else {}
        self._fragment = fragment
        self._on_each_side = 3

    # -- items -----------------------------------------------------------------------
    def items(self) -> Collection[Any]:
        from arvel.support import Collection

        return Collection(self._items)

    def count(self) -> int:
        """Items on the current page."""
        return len(self._items)

    def per_page(self) -> int:
        return self._per_page

    def current_page(self) -> int:
        return self._current_page

    def is_empty(self) -> bool:
        return len(self._items) == 0

    def is_not_empty(self) -> bool:
        return not self.is_empty()

    def first_item(self) -> int | None:
        """1-based index of the first item on this page, or None if empty."""
        if not self._items:
            return None
        return (self._current_page - 1) * self._per_page + 1

    def last_item(self) -> int | None:
        """1-based index of the last item on this page, or None if empty."""
        if not self._items:
            return None
        return (self._current_page - 1) * self._per_page + len(self._items)

    def on_first_page(self) -> bool:
        return self._current_page <= 1

    # -- iteration -------------------------------------------------------------------
    def __iter__(self) -> Iterator[Any]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, index: Any) -> Any:
        return self._items[index]

    # -- query string / fragment -----------------------------------------------------
    def path(self) -> str:
        return self._path

    def get_page_name(self) -> str:
        return self._page_name

    def set_page_name(self, name: str) -> AbstractPaginator:
        self._page_name = name
        return self

    def append(self, key: str, value: Any) -> AbstractPaginator:
        """Append a single key/value to every page URL."""
        self._query[key] = value
        return self

    def appends(self, values: dict[str, Any]) -> AbstractPaginator:
        """Append several key/values to every page URL."""
        self._query.update(values)
        return self

    def with_query_string(self) -> AbstractPaginator:
        """Carry the current request's query string onto every page URL (minus the page key)."""
        self._query.update(_request_query_string(self._page_name))
        return self

    def fragment(self, value: str | None = None) -> Any:
        """Get (no arg) or set (returns self) the URL ``#fragment`` appended to page URLs."""
        if value is None:
            return self._fragment
        self._fragment = value
        return self

    def on_each_side(self, count: int) -> AbstractPaginator:
        """Pages to show on each side of the current page in the link window."""
        self._on_each_side = count
        return self

    # -- urls ------------------------------------------------------------------------
    def url(self, page: int) -> str:
        """The URL for ``page`` — ``path?<page_name>=N&<appended>``, plus any fragment."""
        if page <= 0:
            page = 1
        params = {**self._query, self._page_name: page}
        # doseq: list-valued params emit repeated keys (?tag=a&tag=b), matching the array query params.
        query = urlencode(params, doseq=True)
        fragment = f"#{self._fragment}" if self._fragment else ""
        return f"{self._path}?{query}{fragment}"

    def previous_page_url(self) -> str | None:
        if self._current_page <= 1:
            return None
        return self.url(self._current_page - 1)

    # -- rendering -------------------------------------------------------------------
    async def render(self, view: str | None = None, data: dict[str, Any] | None = None) -> Any:
        """Render the page-link bar to HTML (returns ``Markup``). Override ``view`` to use a
        custom template; extra ``data`` is passed to it. Default templates live under the
        ``pagination`` view namespace."""
        if _view_renderer is None:
            raise RuntimeError(
                "pagination rendering requires the view layer (import arvel.views, which wires "
                "the renderer). Use to_dict()/the accessors if you don't need HTML."
            )
        template = view or self._default_view
        rendered = await _view_renderer(template, {"paginator": self, **(data or {})})
        try:
            from markupsafe import Markup

            # Already escaped by our autoescaping Jinja env; mark safe so templates don't double-escape.
            return Markup(rendered)  # noqa: S704 (autoescaped Jinja)  # nosec B704
        except ImportError:  # pragma: no cover - markupsafe ships with jinja2
            return rendered

    async def links(self, view: str | None = None, data: dict[str, Any] | None = None) -> Any:
        """Alias of:meth:`render`."""
        return await self.render(view, data)

    _default_view = "pagination::default.html"

    # -- subclass contract -----------------------------------------------------------
    def has_more_pages(self) -> bool:  # pragma: no cover - overridden
        raise NotImplementedError

    def next_page_url(self) -> str | None:  # pragma: no cover - overridden
        raise NotImplementedError

    def to_dict(self) -> dict[str, Any]:  # pragma: no cover - overridden
        raise NotImplementedError


# --- length-aware (knows the grand total) -------------------------------------------


class LengthAwarePaginator(AbstractPaginator):
    """A full paginator: knows ``total`` → ``last_page`` and a numbered page window."""

    _default_view = "pagination::default.html"

    def __init__(
        self,
        items: list[Any],
        total: int,
        per_page: int,
        current_page: int | None = None,
        *,
        path: str | None = None,
        query: dict[str, Any] | None = None,
        fragment: str | None = None,
        page_name: str = "page",
    ) -> None:
        super().__init__(
            items,
            per_page,
            current_page,
            path=path,
            query=query,
            fragment=fragment,
            page_name=page_name,
        )
        self._total = total

    def total(self) -> int:
        return self._total

    def last_page(self) -> int:
        return max(1, -(-self._total // self._per_page))  # ceil division

    def has_pages(self) -> bool:
        return self._current_page != 1 or self.has_more_pages()

    def has_more_pages(self) -> bool:
        return self._current_page < self.last_page()

    def next_page_url(self) -> str | None:
        if not self.has_more_pages():
            return None
        return self.url(self._current_page + 1)

    def elements(self) -> list[Any]:
        """The page-link window: a list of ``{page: url}`` bands separated by ``"..."`` strings.

        Mirrors the UrlWindow — a single band when there are few pages, otherwise a
        first band, a slider around the current page, and a last band with separators."""
        last = self.last_page()
        window = self._on_each_side * 2

        if last < window + 8:
            return [self._url_range(1, last)]

        if self._current_page <= window:
            return [self._url_range(1, window + 2), "...", self._url_range(last - 1, last)]

        if self._current_page > last - window:
            return [self._url_range(1, 2), "...", self._url_range(last - (window + 2), last)]

        return [
            self._url_range(1, 2),
            "...",
            self._url_range(
                self._current_page - self._on_each_side, self._current_page + self._on_each_side
            ),
            "...",
            self._url_range(last - 1, last),
        ]

    def _url_range(self, start: int, end: int) -> dict[int, str]:
        return {page: self.url(page) for page in range(start, end + 1)}

    def _link_collection(self) -> list[dict[str, Any]]:
        """the flat ``links`` JSON array: Previous, each page (with ``...`` placeholders),
        then Next — each ``{url, label, active}``."""
        links: list[dict[str, Any]] = [
            {"url": self.previous_page_url(), "label": "&laquo; Previous", "active": False}
        ]
        for element in self.elements():
            if isinstance(element, str):
                links.append({"url": None, "label": element, "active": False})
            else:
                for page, url in element.items():
                    links.append(
                        {"url": url, "label": str(page), "active": page == self._current_page}
                    )
        links.append({"url": self.next_page_url(), "label": "Next &raquo;", "active": False})
        return links

    def to_dict(self) -> dict[str, Any]:
        last = self.last_page()
        return {
            "current_page": self._current_page,
            "data": [_serialize(item) for item in self._items],
            "first_page_url": self.url(1),
            "from": self.first_item(),
            "last_page": last,
            "last_page_url": self.url(last),
            "links": self._link_collection(),
            "next_page_url": self.next_page_url(),
            "path": self._path,
            "per_page": self._per_page,
            "prev_page_url": self.previous_page_url(),
            "to": self.last_item(),
            "total": self._total,
        }


# --- simple (prev/next only) --------------------------------------------------------


class Paginator(AbstractPaginator):
    """A lean prev/next pager: no grand total, so no page count.

    ``has_more`` is normally inferred by fetching one extra row (``per_page + 1``): if an extra
    came back there *is* a next page and the extra is trimmed off."""

    _default_view = "pagination::simple.html"

    def __init__(
        self,
        items: list[Any],
        per_page: int,
        current_page: int | None = None,
        *,
        has_more: bool | None = None,
        path: str | None = None,
        query: dict[str, Any] | None = None,
        fragment: str | None = None,
        page_name: str = "page",
    ) -> None:
        if has_more is None:
            has_more = len(items) > per_page
            items = items[:per_page]
        super().__init__(
            items,
            per_page,
            current_page,
            path=path,
            query=query,
            fragment=fragment,
            page_name=page_name,
        )
        self._has_more = has_more

    def has_pages(self) -> bool:
        return not self.on_first_page() or self.has_more_pages()

    def has_more_pages(self) -> bool:
        return self._has_more

    def next_page_url(self) -> str | None:
        if not self._has_more:
            return None
        return self.url(self._current_page + 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_page": self._current_page,
            "data": [_serialize(item) for item in self._items],
            "first_page_url": self.url(1),
            "from": self.first_item(),
            "next_page_url": self.next_page_url(),
            "path": self._path,
            "per_page": self._per_page,
            "prev_page_url": self.previous_page_url(),
            "to": self.last_item(),
        }


# --- cursor (keyset) ------------------------------------------------------------------------


def encode_cursor(position: dict[str, Any], *, backward: bool = False) -> str:
    """Encode a keyset ``position`` (the ordering columns' values at the seek point) as an
    opaque, URL-safe base64 cursor. This is a wire format, not
    encryption — don't treat it as a security/tamper-proofing boundary."""
    payload = _json.dumps({"p": position, "b": backward}, default=str, sort_keys=True)
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_cursor(cursor: str) -> tuple[dict[str, Any], bool]:
    """Decode a cursor produced by:func:`encode_cursor` back to ``(position, backward)``.
    The cursor is untrusted query-string input, so a malformed one degrades to an empty
    position (the first page, forward) rather than 500ing — matching, which resolves
    an invalid cursor to null."""
    try:
        payload = _json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return payload["p"], bool(payload["b"])
    except ValueError, KeyError, TypeError:  # binascii.Error/JSONDecodeError are ValueErrors
        return {}, False


class CursorPaginator:
    """A keyset (cursor) paginator: pages by an opaque cursor over
        the query's ordering columns instead of ``OFFSET``/page numbers, so paging stays correct even
        as rows are inserted before the cursor mid-scan — the "page drift" the offset-based
    :class:`LengthAwarePaginator`/:class:`Paginator` can't avoid. Iterable over its page of items;
    :meth:`to_dict` mirrors the cursor-paginator JSON shape (DR-0022 object shape — built by
    :meth:`Builder.cursor_paginate`, not constructed directly in normal use)."""

    def __init__(
        self,
        items: list[Any],
        per_page: int,
        *,
        next_cursor: str | None = None,
        prev_cursor: str | None = None,
        path: str | None = None,
        query: dict[str, Any] | None = None,
        cursor_name: str = "cursor",
    ) -> None:
        self._items = list(items)
        self._per_page = max(1, per_page)
        self._next_cursor = next_cursor
        self._prev_cursor = prev_cursor
        self._path = (path if path is not None else resolve_current_path()).rstrip("/") or "/"
        self._query: dict[str, Any] = dict(query) if query else {}
        self._cursor_name = cursor_name

    def items(self) -> Collection[Any]:
        from arvel.support import Collection

        return Collection(self._items)

    def per_page(self) -> int:
        return self._per_page

    def count(self) -> int:
        """Items on this page."""
        return len(self._items)

    def is_empty(self) -> bool:
        return not self._items

    def is_not_empty(self) -> bool:
        return not self.is_empty()

    def on_first_page(self) -> bool:
        return self._prev_cursor is None

    def has_more_pages(self) -> bool:
        return self._next_cursor is not None

    def next_cursor(self) -> str | None:
        return self._next_cursor

    def previous_cursor(self) -> str | None:
        return self._prev_cursor

    def path(self) -> str:
        return self._path

    def _url_for(self, cursor: str | None) -> str | None:
        if cursor is None:
            return None
        params = {**self._query, self._cursor_name: cursor}
        return f"{self._path}?{urlencode(params)}"

    def next_page_url(self) -> str | None:
        return self._url_for(self._next_cursor)

    def previous_page_url(self) -> str | None:
        return self._url_for(self._prev_cursor)

    def __iter__(self) -> Iterator[Any]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, index: Any) -> Any:
        return self._items[index]

    def to_dict(self) -> dict[str, Any]:
        return {
            "data": [_serialize(item) for item in self._items],
            "path": self._path,
            "per_page": self._per_page,
            "next_cursor": self._next_cursor,
            "next_page_url": self.next_page_url(),
            "prev_cursor": self._prev_cursor,
            "prev_page_url": self.previous_page_url(),
        }


__all__ = [
    "AbstractPaginator",
    "CursorPaginator",
    "LengthAwarePaginator",
    "Paginator",
    "decode_cursor",
    "encode_cursor",
    "resolve_current_page",
    "resolve_current_path",
]
