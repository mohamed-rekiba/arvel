"""arvel.database.resources — API Resources: ``JsonResource``/``ResourceCollection``, plus the
JSON:API document renderers ``JsonApiResource``/``JsonApiCollection``. A pure transform layer —
it never imports ``arvel.http``; the http layer recognizes a returned resource and calls
:meth:`JsonResource.to_payload` (the http→database import is legal downward, per the layered
DAG — database sits below http).
"""

from __future__ import annotations

from typing import Any, ClassVar, Self, cast

#: sentinel: a `when`/`when_loaded`/`when_not_none` field this instance omits entirely — stripped
#: from the payload by `to_payload`, rather than serialized as `null`.
MISSING: Any = object()


class ResourceTransformer[M]:
    """The shared transform core: wraps a single model (or any value), turns it into a JSON-safe
    dict via :meth:`to_array`, and offers the ``when*`` conditional-field helpers. Subclasses
    decide the *document* shape (:class:`JsonResource` wraps under a key; :class:`JsonApiResource`
    renders a JSON:API document)."""

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


class JsonResource[M](ResourceTransformer[M]):
    """Wraps a single model (or any value) into the ``{wrap: {...}}`` payload shape. Override
    ``to_array`` to declare the resource's shape; use the ``when*`` helpers for conditional/
    loaded-relation fields."""

    #: the top-level key the payload wraps under; ``None`` disables wrapping.
    wrap: ClassVar[str | None] = "data"

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


def _query_param(request: Any, key: str) -> str | None:
    """A query param via the request's ``query`` accessor; tolerates a bare/absent request so
    the transform layer stays callable outside an HTTP context (queued serialization, tests)."""
    reader = getattr(request, "query", None)
    if not callable(reader):
        return None
    value = reader(key)
    return str(value) if value is not None else None


def _requested_fields(request: Any, resource_type: str) -> set[str] | None:
    """The sparse fieldset for ``resource_type`` (``?fields[<type>]=a,b``), or ``None`` when the
    client didn't constrain it. An empty value means "no attributes", per the media-type spec."""
    raw = _query_param(request, f"fields[{resource_type}]")
    if raw is None:
        return None
    return {name.strip() for name in raw.split(",") if name.strip()}


class JsonApiResource[M](ResourceTransformer[M]):
    """Renders the wrapped model as a JSON:API document: ``data`` with ``type``/``id``/
    ``attributes``, relationship **linkage** for declared relations that are eager-loaded on the
    model (never a lazy load), full related objects under ``included`` when the client asks via
    ``?include=``, and per-type sparse fieldsets via ``?fields[<type>]=``. First-level include
    only; unknown include names and unknown field names are ignored."""

    #: the JSON:API resource ``type`` (plural by convention).
    resource_type: ClassVar[str]

    #: declared relations: relation name (as eager-loaded on the model) → related resource class.
    relationships: ClassVar[dict[str, type[JsonApiResource[Any]]]] = {}

    def attributes(self, request: Any | None = None) -> dict[str, Any]:
        """Override to declare the attribute shape. Defaults to the model dict minus its
        primary key (the key travels as the resource ``id``)."""
        data = self.to_array(request)
        data.pop(self._primary_key(), None)
        return data

    def _primary_key(self) -> str:
        return str(getattr(self.resource, "__primary_key__", "id"))

    def identifier(self) -> dict[str, str]:
        """The ``{type, id}`` resource identifier (linkage shape)."""
        raw: Any = getattr(self.resource, self._primary_key(), None)
        if raw is None:
            to_dict = getattr(self.resource, "to_dict", None)
            if callable(to_dict):
                raw = cast("dict[str, Any]", to_dict()).get(self._primary_key())
            else:
                # the to_array fallback accepts plain mappings; the id must come from the
                # same place
                getter = getattr(self.resource, "get", None)
                if callable(getter):
                    raw = getter(self._primary_key())
        return {"type": self.resource_type, "id": str(raw)}

    def _loaded_relations(self) -> dict[str, Any]:
        relations = getattr(self.resource, "_relations", None)
        if not isinstance(relations, dict):
            return {}
        loaded = cast("dict[str, Any]", relations)
        return {name: loaded[name] for name in self.relationships if name in loaded}

    def resource_object(self, request: Any | None) -> dict[str, Any]:
        """The full resource object: identifier + (sparse) attributes + loaded linkage."""
        fields = _requested_fields(request, self.resource_type)
        attributes = _strip_missing(self.attributes(request))
        if fields is not None:
            attributes = {k: v for k, v in attributes.items() if k in fields}
        obj: dict[str, Any] = {**self.identifier(), "attributes": attributes}
        linkage: dict[str, Any] = {}
        for name, related in self._loaded_relations().items():
            resource_cls = self.relationships[name]
            if isinstance(related, (list, tuple)):
                many: list[Any] = list(cast("tuple[Any, ...]", related))
                linkage[name] = {"data": [resource_cls(m).identifier() for m in many]}
            elif related is None:
                linkage[name] = {"data": None}
            else:
                linkage[name] = {"data": resource_cls(related).identifier()}
        if linkage:
            obj["relationships"] = linkage
        return obj

    def included_objects(
        self, request: Any | None, seen: set[tuple[str, str]]
    ) -> list[dict[str, Any]]:
        """The ``included`` members this resource contributes for the request's ``?include=``,
        deduplicated across the document via ``seen``."""
        raw = _query_param(request, "include")
        if not raw:
            return []
        wanted = {name.strip() for name in raw.split(",") if name.strip()}
        included: list[dict[str, Any]] = []
        for name, related in self._loaded_relations().items():
            if name not in wanted:
                continue
            resource_cls = self.relationships[name]
            items: list[Any] = (
                list(cast("tuple[Any, ...]", related))
                if isinstance(related, (list, tuple))
                else [related]
            )
            for model in items:
                if model is None:
                    continue
                resource = resource_cls(model)
                key = (resource.resource_type, resource.identifier()["id"])
                if key in seen:
                    continue
                seen.add(key)
                included.append(resource.resource_object(request))
        return included

    def to_payload(self, request: Any | None = None) -> dict[str, Any]:
        document: dict[str, Any] = {"data": self.resource_object(request)}
        included = self.included_objects(request, set())
        if included:
            document["included"] = included
        document.update(self._additional)
        return document

    @classmethod
    def collection(cls, models: Any) -> JsonApiCollection[Self]:
        return JsonApiCollection(cls, models)


class JsonApiCollection[R: JsonApiResource[Any]]:
    """A JSON:API collection document over a plain iterable or a paginator; a paginator
    contributes top-level ``links`` (first/last/prev/next) and ``meta``."""

    def __init__(self, resource_cls: type[R], models: Any) -> None:
        self.resource_cls = resource_cls
        self.resource = models
        self._additional: dict[str, Any] = {}

    def additional(self, meta: dict[str, Any]) -> Self:
        self._additional = dict(meta)
        return self

    def to_payload(self, request: Any | None = None) -> dict[str, Any]:
        from arvel.pagination import AbstractPaginator

        document: dict[str, Any]
        items: list[Any]
        if isinstance(self.resource, AbstractPaginator):
            source = self.resource.to_dict()
            items = list(self.resource.items())
            document = {
                "data": [self.resource_cls(m).resource_object(request) for m in items],
                "links": _paginator_links(source),
                "meta": _paginator_meta(source),
            }
        else:
            items = list(cast("list[Any]", self.resource))
            document = {"data": [self.resource_cls(m).resource_object(request) for m in items]}
        seen: set[tuple[str, str]] = set()
        included: list[dict[str, Any]] = []
        for model in items:
            included.extend(self.resource_cls(model).included_objects(request, seen))
        if included:
            document["included"] = included
        document.update(self._additional)
        return document


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


__all__ = [
    "MISSING",
    "JsonApiCollection",
    "JsonApiResource",
    "JsonResource",
    "ResourceCollection",
]
