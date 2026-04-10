"""ResourceCollection — batch model-to-response transformation with pagination.

Transforms a list (or ``ArvelCollection``, ``PaginatedResult``,
``CursorResult``) of models through a ``JsonResource`` subclass and
produces a structured response dict with optional pagination metadata.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

from arvel.data.pagination import CursorResult, PaginatedResult
from arvel.http.resources.json_resource import _strip_missing

if TYPE_CHECKING:
    from arvel.http.resources.json_resource import JsonResource


class ResourceCollection[T]:
    """Transforms a collection of models using a ``JsonResource`` subclass.

    Accepts plain lists, ``ArvelCollection``, ``PaginatedResult``, or
    ``CursorResult``.  Pagination metadata is appended automatically
    when the input is a paginated type.
    """

    def __init__(
        self,
        resource_class: type[JsonResource[T]],
        items: list[T] | PaginatedResult[T] | CursorResult[T],
    ) -> None:
        self.resource_class = resource_class
        self._raw = items
        self._additional: dict[str, Any] = {}

    def additional(self, data: dict[str, Any]) -> Self:
        """Merge extra data into the top-level response (fluent API)."""
        self._additional.update(data)
        return self

    def to_response(self) -> dict[str, Any] | list[dict[str, Any]]:
        """Transform all items and return the response dict (or list if unwrapped)."""
        items: list[Any]
        meta: dict[str, Any] | None = None

        if isinstance(self._raw, PaginatedResult):
            items = self._raw.data
            meta = {
                "total": self._raw.total,
                "page": self._raw.page,
                "per_page": self._raw.per_page,
                "last_page": self._raw.last_page,
                "has_more": self._raw.has_more,
            }
        elif isinstance(self._raw, CursorResult):
            items = self._raw.data
            meta = {
                "next_cursor": self._raw.next_cursor,
                "has_more": self._raw.has_more,
            }
        else:
            items = list(self._raw)

        transformed = [_strip_missing(self.resource_class(item).to_dict()) for item in items]

        wrap_key = self.resource_class.__wrap__
        if wrap_key is None:
            if self._additional:
                return [{**item, **self._additional} for item in transformed]
            return transformed

        result: dict[str, Any] = {wrap_key: transformed}
        if meta is not None:
            result["meta"] = meta
        result.update(self._additional)
        return result
