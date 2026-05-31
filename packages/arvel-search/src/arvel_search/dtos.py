"""Search data transfer objects."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _empty_filters() -> dict[str, object]:
    return {}


class SearchResult(BaseModel):
    """A normalized hit set returned by every engine.

    ``ids`` is the ordered list of document keys (strings); ``total`` is the full
    match count before limit/offset; ``raw`` is the engine's native response.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    ids: list[str] = Field(default_factory=list)
    total: int = 0
    raw: Any = None


@dataclass(frozen=True)
class SearchQuery:
    """Everything an engine needs to run one search.

    ``model`` and ``columns`` are only used by the database driver (SQL ILIKE);
    network drivers read ``index``/``query``/``filters`` and ignore the rest.
    """

    index: str
    query: str = ""
    limit: int | None = None
    offset: int = 0
    filters: Mapping[str, object] = field(default_factory=_empty_filters)
    model: type[Any] | None = None
    columns: Sequence[str] = ()
    key_name: str = "id"


__all__ = ["SearchQuery", "SearchResult"]
