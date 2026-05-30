"""Event base class — Pydantic BaseModel with auto-registration (ADR-037)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

# Maps "module.ClassName" -> Event subclass. Populated by Event.__init_subclass__.
EventRegistry: dict[str, type[Event]] = {}


class Event(BaseModel):
    """Base class for all in-process events.

    Subclasses declare payload fields as Pydantic fields.
    Subclasses auto-register in ``EventRegistry`` via ``__init_subclass__``.
    """

    model_config = ConfigDict(frozen=True)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        key = f"{cls.__module__}.{cls.__qualname__}"
        EventRegistry[key] = cls


__all__ = ["Event", "EventRegistry"]
