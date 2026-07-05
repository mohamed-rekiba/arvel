"""arvel.database.resources — API Resources: ``JsonResource``/``ResourceCollection`` (``eloquent-resources`` 13.x parity). A pure transform layer — it never imports ``arvel.http``; the
http layer recognizes a returned resource and calls:meth:`JsonResource.to_payload` (the
http→database import is legal downward, per the layered DAG — database sits below http).
"""

from __future__ import annotations

from typing import Any, ClassVar, Self, cast

#: sentinel: a `when`/`when_loaded`/`when_not_none` field this instance omits entirely — stripped
#: from the payload by `to_payload`, rather than serialized as `null`.
MISSING: Any = object()


class JsonResource[M]:
    """Wraps a single model (or any value) and transforms it to a JSON-safe dict via
    :meth:`to_array`. Override ``to_array`` to declare the resource's shape; use the ``when*``
        helpers for conditional/loaded-relation fields."""

    #: the top-level key the payload wraps under; ``None`` disables wrapping.
    wrap: ClassVar[str | None] = "data"

    def __init__(self, resource: M) -> None:
        self.resource = resource
        self._additional: dict[str, Any] = {}

    def to_array(self, request: Any | None = None) -> dict[str, Any]:
        """Override to declare the resource's shape. Defaults to the wrapped value's
        ``to_dict()`` (a plain ``Model``), or the value itself if it's already a mapping."""
        to_dict = getattr(self.resource, "to_dict", None)
        if callable(to_dict):
            return cast("dict[str, Any]", to_dict())
        return cast("dict[str, Any]", dict(self.resource))  # type: ignore[call-overload]

    # --- conditional fields -------------------------------------------------------
    def when(self, condition: bool, value: Any, default: Any = MISSING) -> Any:
        """``value`` (called if callable) when ``condition``, else ``default`` (``MISSING`` by
        default — a key set to ``MISSING`` is stripped from the payload entirely)."""
        if not condition:
            return default
        return value() if callable(value) else value

    def when_not_none(self, value: Any) -> Any:
        """``value`` if not ``None``, else ``MISSING``."""
        return self.when(value is not None, value)

    def when_loaded(self, relation: str, cb: Any = None) -> Any:
        """The eager-loaded relation's value (or ``cb(loaded_value)`` if given), or ``MISSING``
        when ``relation`` wasn't eager-loaded on the wrapped model."""
        maybe_relations = getattr(self.resource, "_relations", None)
        if not isinstance(maybe_relations, dict):
            return MISSING
        relations = cast("dict[str, Any]", maybe_relations)
        if relation not in relations:
            return MISSING
        loaded: Any = relations[relation]
        if cb is None:
            return loaded
        result: Any = cb(loaded)
        return result

    def merge_when(self, condition: bool, mapping: dict[str, Any]) -> dict[str, Any]:
        """``mapping`` when ``condition``, else ``{}`` — spread the result
        into ``to_array``'s returned dict, e.g. ``{**self.merge_when(cond, {...}), "id":...}``."""
        return dict(mapping) if condition else {}

    # --- meta / wrapping -----------------------------------------------------------
    def additional(self, meta: dict[str, Any]) -> Self:
        """Attach extra top-level metadata merged alongside the wrapped ``data`` key."""
        self._additional = dict(meta)
        return self

    def to_payload(self, request: Any | None = None) -> dict[str, Any]:
        """The final JSON-safe payload: ``to_array`` with ``MISSING`` fields stripped, wrapped
        under:attr:`wrap` (no wrapping at all when ``wrap`` is ``None`` — never double-wrapped),
        plus any:meth:`additional` meta merged in at the top level."""
        data = _strip_missing(self.to_array(request))
        payload: dict[str, Any] = {self.wrap: data} if self.wrap else dict(data)
        payload.update(self._additional)
        return payload

    @classmethod
    def collection(cls, models: Any) -> ResourceCollection[Self]:
        """A:class:`ResourceCollection` mapping ``cls`` over ``models`` — a plain iterable, or a
        :class:`~arvel.pagination.AbstractPaginator` (whose ``meta``/``links`` travel alongside
                the wrapped ``data``, the paginated-resource response shape)."""
        return ResourceCollection(cls, models)


def _strip_missing(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value is not MISSING}


class ResourceCollection[R: JsonResource[Any]]:
    """A collection of:class:`JsonResource` built by:meth:`JsonResource.collection` — maps
    ``resource_cls`` over every item. Built from a paginator, ``meta``/``links`` travel alongside
    the wrapped ``data``; the collection wraps under
    ``resource_cls.wrap`` (the same key a lone resource of that class would use)."""

    def __init__(self, resource_cls: type[R], models: Any) -> None:
        self.resource_cls = resource_cls
        self.resource = models
        self._additional: dict[str, Any] = {}

    def additional(self, meta: dict[str, Any]) -> Self:
        self._additional = dict(meta)
        return self

    def to_payload(self, request: Any | None = None) -> dict[str, Any]:
        from arvel.pagination import AbstractPaginator

        wrap = self.resource_cls.wrap
        if isinstance(self.resource, AbstractPaginator):
            source = self.resource.to_dict()
            data = [
                _strip_missing(self.resource_cls(item).to_array(request))
                for item in self.resource.items()
            ]
            payload: dict[str, Any] = {
                (wrap or "data"): data,
                "links": _paginator_links(source),
                "meta": _paginator_meta(source),
            }
        else:
            data = [
                _strip_missing(self.resource_cls(item).to_array(request)) for item in self.resource
            ]
            payload = {wrap: data} if wrap else {"data": data}
        payload.update(self._additional)
        return payload


def _paginator_links(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "first": source.get("first_page_url"),
        "last": source.get("last_page_url"),
        "prev": source.get("prev_page_url"),
        "next": source.get("next_page_url"),
    }


def _paginator_meta(source: dict[str, Any]) -> dict[str, Any]:
    keys = ("current_page", "from", "last_page", "path", "per_page", "to", "total")
    return {key: source[key] for key in keys if key in source}


__all__ = ["MISSING", "JsonResource", "ResourceCollection"]
