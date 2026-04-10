"""Transaction — transactional boundary with SAVEPOINT nesting.

Groups multiple repository operations into a single transaction.
Normal exit commits; exception exit rolls back.

Subclasses should expose repositories as typed ``@property`` methods
using ``_get_repo()`` for full type checker support::

    class AppTransaction(Transaction):
        @property
        def users(self) -> UserRepository:
            return self._get_repo(UserRepository)

The ``__getattr__`` fallback still works for annotation-declared
repositories but returns ``Any`` to the type checker.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from functools import lru_cache
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Self, cast, get_type_hints

from arvel.data.repository import Repository


@lru_cache(maxsize=64)
def _cached_type_hints(cls: type) -> MappingProxyType[str, Any]:
    """Cache ``get_type_hints()`` per class — the result is stable after class creation.

    Returns a read-only view to prevent accidental mutation of the cache.
    """
    return MappingProxyType(get_type_hints(cls))


if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from types import TracebackType

    from sqlalchemy.ext.asyncio import AsyncSession

    from arvel.data.observer import ObserverRegistry


class Transaction:
    """Transaction context manager for atomic repository operations.

    Preferred pattern — typed ``@property`` methods::

        class AppTransaction(Transaction):
            @property
            def users(self) -> UserRepository:
                return self._get_repo(UserRepository)

    Legacy pattern — annotation-based (returns ``Any`` to checkers)::

        class AppTransaction(Transaction):
            users: UserRepository

    When ``DatabaseServiceProvider`` is registered, both *session* and
    *observer_registry* are optional::

        async with AppTransaction() as tx:
            user = await tx.users.create(data)
    """

    def __init__(
        self,
        *,
        session: AsyncSession | None = None,
        observer_registry: ObserverRegistry | None = None,
    ) -> None:
        if session is None:
            from arvel.data.model import ArvelModel

            resolver = ArvelModel._session_resolver
            if resolver is None:
                msg = (
                    "No session provided and no default session resolver is configured. "
                    "Either pass a session explicitly or register "
                    "DatabaseServiceProvider in your bootstrap/providers.py."
                )
                raise RuntimeError(msg)
            session = resolver()

        if observer_registry is None:
            from arvel.data.observer import ObserverRegistry as _ObserverRegistry

            observer_registry = _ObserverRegistry()

        self._session = session
        self._observer_registry = observer_registry
        self._repos: dict[type, Repository[Any]] = {}
        self._repos_by_name: dict[str, Repository[Any]] = {}
        self._nesting_depth = 0

    def _get_repo[R: Repository[Any]](self, repo_cls: type[R]) -> R:
        """Lazily create and cache a repository instance.

        Preserves the concrete repository type through the generic
        ``R`` bound, so ``self._get_repo(UserRepository)`` returns
        ``UserRepository`` to the type checker.
        """
        cached = self._repos.get(repo_cls)
        if cached is not None:
            # Safe: the cache key *is* the class we're casting to — see
            # the assignment three lines below.
            return cast("R", cached)
        repo = repo_cls(session=self._session, observer_registry=self._observer_registry)
        self._repos[repo_cls] = repo
        return repo

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)

        if name in self._repos_by_name:
            return self._repos_by_name[name]

        hints = _cached_type_hints(type(self))
        repo_cls = hints.get(name)
        if repo_cls is not None and isinstance(repo_cls, type) and issubclass(repo_cls, Repository):
            repo = self._get_repo(repo_cls)
            self._repos_by_name[name] = repo
            return repo

        raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")

    async def __aenter__(self) -> Self:
        if self._nesting_depth == 0:
            if not self._session.in_transaction():
                await self._session.begin()
        else:
            await self._session.begin_nested()
        self._nesting_depth += 1
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self._nesting_depth -= 1
        if exc_type is not None:
            await self._session.rollback()
        elif self._nesting_depth == 0:
            await self._session.commit()

    @asynccontextmanager
    async def nested(self) -> AsyncGenerator[Self]:
        """Create a nested savepoint within the current transaction."""
        nested = await self._session.begin_nested()
        self._nesting_depth += 1
        try:
            yield self
        except Exception:
            await nested.rollback()
            self._nesting_depth -= 1
            raise
        else:
            await nested.commit()
            self._nesting_depth -= 1
