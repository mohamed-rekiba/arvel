"""``JsonResource[T]`` + ``ResourceCollection[T]`` — typed response transformation.

A ``ResourceCollection`` can be backed by either a plain ``list[T]`` (the
classic Laravel ``data``-only envelope) or any object that quacks like a
paginator. The paginator path is structurally typed via ``Paginatable[T]``
so the HTTP layer doesn't need to import from ``arvel.database`` (ADR-016).
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Callable, Mapping
from typing import Any, ClassVar, Generic, Protocol, Self, TypeVar, runtime_checkable

from pydantic import BaseModel
from starlette.responses import JSONResponse

T = TypeVar("T")

# Sentinel returned by when() / when_loaded() when their condition is false.
# Stripped from the output dict automatically by the __init_subclass__ wrapper.
_MISSING = object()


@runtime_checkable
class Paginatable(Protocol[T]):
    """Anything that walks like ``arvel.database.Paginator`` for our purposes.

    The collection layer only needs ``items`` (for transformation) and
    ``to_dict(items_serializer=, base_url=, query=)`` (for envelope
    composition). Concrete page-vs-simple-vs-cursor differences live inside
    the paginator's own ``to_dict``.

    The Protocol is invariant in ``T`` because ``items_serializer`` puts
    ``T`` in contravariant position.
    """

    @property
    def items(self) -> list[T]: ...

    def to_dict(
        self,
        items_serializer: Callable[[T], Any] | None = None,
        *,
        base_url: str | None = None,
        query: Mapping[str, str] | None = None,
    ) -> dict[str, Any]: ...


def _looks_like_paginator(value: Any) -> bool:
    return (
        not isinstance(value, list)
        and hasattr(value, "items")
        and callable(getattr(value, "to_dict", None))
    )


def _derive_url_context(request: Any) -> tuple[str | None, dict[str, str] | None]:
    """Best-effort extraction of ``(base_url, query)`` from a Starlette-like request.

    Returns ``(None, None)`` when the request doesn't expose ``.url`` /
    ``.query_params`` — callers fall back to integer page numbers.

    ``page`` and ``cursor`` are stripped from the query before merging: those
    keys belong to the paginator, not the inbound request.
    """
    url = getattr(request, "url", None)
    if url is None:
        return None, None
    scheme = getattr(url, "scheme", None)
    netloc = getattr(url, "netloc", None)
    path = getattr(url, "path", None)
    if not scheme or not netloc or path is None:
        return None, None
    base = f"{scheme}://{netloc}{path}"

    raw_query = getattr(request, "query_params", None)
    if raw_query is None:
        return base, None
    try:
        query: dict[str, str] = {str(k): str(v) for k, v in raw_query.items()}
    except AttributeError, TypeError:
        return base, None
    query.pop("page", None)
    query.pop("cursor", None)
    return base, query


class ResourceResponse(JSONResponse):
    """Starlette ``JSONResponse`` built from a resource ``to_dict`` envelope."""


class JsonResource(Generic[T]):
    """Transform a single domain object into a JSON-ready dict.

    Subclasses set the generic parameter and implement ``to_dict(request)``.
    Optionally set ``schema: ClassVar[type[BaseModel]]`` to surface an OpenAPI
    schema for this resource — opt-in only.

    Any value returned as ``self.when(...)`` or ``self.when_loaded(...)`` that
    evaluates to the internal sentinel is automatically stripped from the dict
    returned by ``to_dict()``.
    """

    schema: ClassVar[type[BaseModel] | None] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Wrap every concrete to_dict() so _MISSING sentinels drop out and any
        # caller-supplied .additional({...}) extras merge in last.
        if "to_dict" in cls.__dict__:
            _orig: Any = cls.__dict__["to_dict"]

            def _wrapped(self: Any, request: Any, *, _f: Any = _orig) -> dict[str, Any]:
                raw = _f(self, request)
                cleaned = {k: v for k, v in raw.items() if v is not _MISSING}
                extras: Mapping[str, Any] = getattr(self, "_additional", {})
                if extras:
                    cleaned.update(extras)
                return cleaned

            cls.to_dict = _wrapped  # type: ignore[method-assign]

    def __init__(self, resource: T) -> None:
        self.resource: T = resource
        self._additional: dict[str, Any] = {}

    @abstractmethod
    def to_dict(self, request: Any) -> dict[str, Any]: ...

    def additional(self, extra: Mapping[str, Any]) -> Self:
        """Merge extra root-level keys into the dict returned by ``to_dict``.

        Extras win on key clashes. Chainable.
        """
        self._additional.update(extra)
        return self

    @classmethod
    def collection(cls, resources: list[T] | Paginatable[T]) -> ResourceCollection[T]:
        """Wrap ``resources`` (a list or any paginator) in a ``ResourceCollection``.

        With a list, the output is ``{"data": [...]}`` — overridable via
        ``ResourceCollection.wrap``. With a paginator, the output mirrors the
        paginator's own ``{data, meta, links}`` envelope with each item
        transformed by this resource class.
        """
        if isinstance(resources, list):
            return ResourceCollection(resources, cls)
        if not _looks_like_paginator(resources):
            raise TypeError(
                f"{cls.__name__}.collection() expects a list or paginator, "
                f"got {type(resources).__name__}."
            )
        return ResourceCollection(list(resources.items), cls, paginator=resources)

    def when(self, condition: Any, value: Any) -> Any:
        """Return *value* when *condition* is truthy, otherwise a missing sentinel.

        The sentinel is stripped from the dict returned by ``to_dict()`` automatically.
        """
        return value if condition else _MISSING

    def when_loaded(self, relation: str) -> Any:
        """Return the relation value if it's already in the resource's ``__dict__``.

        Never triggers a lazy load — safe to call on SQLAlchemy models.
        """
        resource_dict: dict[str, Any] = getattr(self.resource, "__dict__", {})
        if relation in resource_dict:
            return resource_dict[relation]
        return _MISSING

    def merge_when(self, condition: Any, data: dict[str, Any]) -> dict[str, Any]:
        """Return *data* when *condition* is truthy, otherwise an empty dict."""
        return dict(data) if condition else {}

    def response(
        self,
        request: Any,
        *,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> ResourceResponse:
        """Build a Starlette JSON response from ``to_dict(request)``."""
        return ResourceResponse(
            content=self.to_dict(request),
            status_code=status_code,
            headers=dict(headers) if headers else None,
        )


class ResourceCollection(Generic[T]):
    """Transform a list (or paginator) of domain objects under one envelope.

    Default ``wrap`` returns ``{"data": data}`` for the list path. The
    paginator path bypasses ``wrap`` — its envelope is whatever the paginator's
    own ``to_dict`` returns, with items transformed by ``resource_cls``.
    """

    def __init__(
        self,
        resources: list[T],
        resource_cls: type[JsonResource[T]],
        *,
        paginator: Paginatable[T] | None = None,
    ) -> None:
        self._resources = resources
        self._resource_cls = resource_cls
        self._paginator = paginator
        self._additional: dict[str, Any] = {}

    def to_dict(self, request: Any) -> dict[str, Any]:
        if self._paginator is not None:
            base_url, query = _derive_url_context(request)
            body = self._paginator.to_dict(
                items_serializer=lambda r: self._resource_cls(r).to_dict(request),
                base_url=base_url,
                query=query,
            )
        else:
            data = [self._resource_cls(r).to_dict(request) for r in self._resources]
            body = self.wrap(data)

        if self._additional:
            body.update(self._additional)
        return body

    def wrap(self, data: list[dict[str, Any]]) -> dict[str, Any]:
        return {"data": data}

    def additional(self, extra: Mapping[str, Any]) -> Self:
        """Merge extra root-level keys into the envelope returned by ``to_dict``.

        Extras win on key clashes — they merge after the default envelope (or
        the paginator's envelope) is built. Chainable.
        """
        self._additional.update(extra)
        return self

    def response(
        self,
        request: Any,
        *,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> ResourceResponse:
        """Build a Starlette JSON response from ``to_dict(request)``."""
        return ResourceResponse(
            content=self.to_dict(request),
            status_code=status_code,
            headers=dict(headers) if headers else None,
        )


__all__ = ["JsonResource", "Paginatable", "ResourceCollection", "ResourceResponse"]
