"""JsonResource — type-safe model-to-response transformation.

``JsonResource[T]`` wraps a model instance and transforms it into a
structured API response dict.  Subclass and override ``to_dict()`` to
control which fields are exposed.

Conditional helpers (``when``, ``when_loaded``, ``when_not_null``)
return ``MISSING`` when their condition is false — ``to_response()``
recursively strips those entries before serialization.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Self

from arvel.http.resources.missing_value import MISSING, _MissingValue

if TYPE_CHECKING:
    from collections.abc import Mapping

    from arvel.data.pagination import CursorResult, PaginatedResult
    from arvel.http.resources.collection import ResourceCollection


def _strip_missing(data: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively remove entries whose value is MISSING."""
    result: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, _MissingValue):
            continue
        if isinstance(value, dict):
            result[key] = _strip_missing(value)
        else:
            result[key] = value
    return result


class JsonResource[T]:
    """Base API resource for transforming a model instance into a response dict.

    Override ``to_dict()`` in subclasses to control field selection.  The
    default implementation delegates to ``model_dump()`` on the wrapped
    instance (or ``vars()`` if ``model_dump`` is not available).

    Subclasses can narrow the return type of ``to_dict()`` to a ``TypedDict``
    for full type safety — ``Mapping[str, Any]`` accepts both ``dict[str, Any]``
    and any ``TypedDict`` as valid return types.

    Set ``__wrap__`` to change the top-level response key (default ``"data"``).
    Set it to ``None`` to return the dict unwrapped.
    """

    __wrap__: ClassVar[str | None] = "data"

    def __init__(self, resource: T) -> None:
        self.resource: T = resource
        self._additional: dict[str, Any] = {}

    def to_dict(self) -> Mapping[str, Any]:
        """Transform the model into a plain dict.

        Override in subclasses to select specific fields.  The base
        implementation returns all columns via ``model_dump()`` (or
        ``vars()`` as fallback).
        """
        model_dump = getattr(self.resource, "model_dump", None)
        if callable(model_dump):
            return model_dump()
        return dict(vars(self.resource))

    def to_response(self) -> dict[str, Any]:
        """Wrap ``to_dict()`` output, strip ``MISSING`` values, merge additional data."""
        raw = self.to_dict()
        cleaned = _strip_missing(raw)

        wrap_key = self.__class__.__wrap__
        if wrap_key is not None:
            result: dict[str, Any] = {wrap_key: cleaned}
        else:
            result = dict(cleaned)

        result.update(self._additional)
        return result

    def additional(self, data: dict[str, Any]) -> Self:
        """Merge extra data into the top-level response (fluent API)."""
        self._additional.update(data)
        return self

    # ──── Conditional helpers ────

    def when(self, condition: bool, value: Any, *, default: Any = MISSING) -> Any:
        """Include *value* when *condition* is truthy, otherwise *default* (or MISSING)."""
        if condition:
            return value
        return default

    def when_loaded(
        self,
        relationship: str,
        resource_class: type[JsonResource[Any]] | None = None,
    ) -> Any:
        """Include a relationship only when it's eagerly loaded on the model.

        If the relationship is loaded:
        - With *resource_class*: transforms items via the resource (list → list, single → single)
        - Without *resource_class*: returns the raw value

        If the relationship is not loaded, returns ``MISSING``.

        Raises ``ValueError`` if *relationship* is not a valid relationship or attribute.
        """
        is_loaded_fn = getattr(self.resource, "is_relation_loaded", None)
        if is_loaded_fn is None:
            msg = f"Resource model {type(self.resource).__name__} has no is_relation_loaded method"
            raise ValueError(msg)

        loaded = is_loaded_fn(relationship)
        exists = hasattr(self.resource, relationship)

        if not loaded and not exists:
            get_relationships = getattr(type(self.resource), "get_relationships", None)
            if get_relationships is not None:
                known = get_relationships()
                if relationship not in known:
                    cls_name = type(self.resource).__name__
                    msg = f"Relationship '{relationship}' does not exist on {cls_name}"
                    raise ValueError(msg)
            else:
                cls_name = type(self.resource).__name__
                msg = f"Relationship '{relationship}' does not exist on {cls_name}"
                raise ValueError(msg)

        if not loaded:
            return MISSING

        raw_value = getattr(self.resource, relationship)

        if resource_class is None:
            return raw_value

        if isinstance(raw_value, list):
            return [resource_class(item).to_dict() for item in raw_value]

        return resource_class(raw_value).to_dict()

    def when_not_null(self, attribute: str) -> Any:
        """Include attribute value only when it's not None."""
        value = getattr(self.resource, attribute)
        if value is None:
            return MISSING
        return value

    # ──── Collection factory ────

    @classmethod
    def collection(
        cls,
        items: list[T] | PaginatedResult[T] | CursorResult[T],
    ) -> ResourceCollection[T]:
        """Create a ``ResourceCollection`` that transforms each item via this resource class."""
        from arvel.http.resources.collection import ResourceCollection

        return ResourceCollection(cls, items)
