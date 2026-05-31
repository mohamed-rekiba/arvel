"""Search facade — classmethod access to the bound SearchManager/engine.

Bound by ``SearchServiceProvider.boot()``. :meth:`fake` swaps the active engine
for an in-memory :class:`SearchFake` so tests can assert on index writes without
a server.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from arvel_search.exceptions import SearchEngineNotConfigured

if TYPE_CHECKING:
    from arvel_search.engine import Engine
    from arvel_search.fake import SearchFake
    from arvel_search.manager import SearchManager


class Search:
    manager: ClassVar[SearchManager | None] = None
    _faked: ClassVar[Engine | None] = None

    @classmethod
    def bind(cls, manager: SearchManager) -> None:
        cls.manager = manager
        cls._faked = None

    @classmethod
    def engine(cls, name: str | None = None) -> Engine:
        if cls._faked is not None:
            return cls._faked
        if cls.manager is None:
            raise SearchEngineNotConfigured
        return cls.manager.engine(name)

    @classmethod
    def active_engine_or_none(cls) -> Engine | None:
        """Return the bound engine, or ``None`` when search isn't configured.

        Lets ``Searchable`` models stay usable in DB-only contexts (no provider)
        — sync just becomes a no-op instead of raising.
        """
        if cls._faked is not None:
            return cls._faked
        if cls.manager is None:
            return None
        return cls.manager.engine()

    @classmethod
    def is_faked(cls) -> bool:
        return cls._faked is not None

    @classmethod
    def fake(cls) -> SearchFake:
        from arvel_search.fake import SearchFake

        fake = SearchFake()
        cls._faked = fake
        return fake

    @classmethod
    def restore(cls) -> None:
        """Undo :meth:`fake` — route back to the real manager."""
        cls._faked = None


__all__ = ["Search"]
