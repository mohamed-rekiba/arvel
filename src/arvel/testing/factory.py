"""Model factory — generates realistic ArvelModel instances for tests.

Each factory subclass maintains a per-class sequence counter. Override
``defaults()`` and call ``cls._next_seq()`` to embed unique values::

    class UserFactory(ModelFactory[User]):
        __model__ = User

        @classmethod
        def defaults(cls) -> dict[str, Any]:
            seq = cls._next_seq()
            return {"name": f"User {seq}", "email": f"user{seq}@test.com"}

        @classmethod
        def state_admin(cls) -> dict[str, Any]:
            return {"name": "Admin User"}

Usage::

    user = UserFactory.make()
    user = await UserFactory.create(session=session)
    user = UserFactory.state("admin").make()
    users = await UserFactory.create_many(5, session=session)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, cast

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class FactoryBuilder[T]:
    """Immutable builder returned by ``ModelFactory.state()`` for chained creation."""

    def __init__(self, factory_cls: type[ModelFactory[T]], state_overrides: dict[str, Any]) -> None:
        self._factory_cls = factory_cls
        self._state_overrides = state_overrides

    def make(self, **overrides: Any) -> T:
        merged = {**self._state_overrides, **overrides}
        return self._factory_cls.make(**merged)

    async def create(self, *, session: AsyncSession, **overrides: Any) -> T:
        merged = {**self._state_overrides, **overrides}
        return await self._factory_cls.create(session=session, **merged)

    async def create_many(self, count: int, *, session: AsyncSession, **overrides: Any) -> list[T]:
        merged = {**self._state_overrides, **overrides}
        return await self._factory_cls.create_many(count, session=session, **merged)

    def make_batch(self, count: int, **overrides: Any) -> list[T]:
        merged = {**self._state_overrides, **overrides}
        return self._factory_cls.make_batch(count, **merged)


class ModelFactory[T]:
    """Base factory for generating ArvelModel instances.

    ``make()`` returns in-memory instances, ``create()`` persists to
    the database, ``batch()`` / ``make_batch()`` produce multiple.

    Sequence-based uniqueness: call ``_next_seq()`` inside ``defaults()``
    to get an auto-incrementing integer unique per factory class.
    """

    __model__: ClassVar[type[Any]]
    _counter: ClassVar[int] = 0

    @classmethod
    def _next_seq(cls) -> int:
        """Return an auto-incrementing sequence number unique to this factory."""
        cls._counter += 1
        return cls._counter

    @classmethod
    def _reset_seq(cls) -> None:
        """Reset the sequence counter (useful in test teardown)."""
        cls._counter = 0

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        """Override in subclasses to provide default field values.

        Use ``cls._next_seq()`` for fields that require uniqueness::

            @classmethod
            def defaults(cls) -> dict[str, Any]:
                seq = cls._next_seq()
                return {"name": f"User {seq}", "email": f"user{seq}@test.com"}
        """
        return {}

    @classmethod
    def state(cls, name: str) -> FactoryBuilder[T]:
        """Return a builder pre-loaded with the named state's overrides.

        States are defined as ``state_<name>()`` class methods that return dicts::

            @classmethod
            def state_admin(cls) -> dict[str, Any]:
                return {"role": "admin"}
        """
        method_name = f"state_{name}"
        method = getattr(cls, method_name, None)
        if method is None:
            msg = f"Unknown state '{name}' on {cls.__name__}. Define '{method_name}()'."
            raise ValueError(msg)
        return FactoryBuilder(cls, method())

    @classmethod
    def make(cls, **overrides: Any) -> T:
        """Create an in-memory model instance (not persisted)."""
        attrs = {**cls.defaults(), **overrides}
        return cast("T", cls.__model__(**attrs))

    @classmethod
    async def create(cls, *, session: AsyncSession, **overrides: Any) -> T:
        """Create and persist a model instance to the database."""
        instance = cls.make(**overrides)
        session.add(instance)
        await session.flush()
        await session.refresh(instance)
        return instance

    @classmethod
    def make_batch(cls, count: int, **overrides: Any) -> list[T]:
        """Create multiple in-memory instances."""
        return [cls.make(**overrides) for _ in range(count)]

    @classmethod
    async def batch(cls, count: int, *, session: AsyncSession, **overrides: Any) -> list[T]:
        """Create and persist multiple instances."""
        instances = []
        for _ in range(count):
            inst = await cls.create(session=session, **overrides)
            instances.append(inst)
        return instances

    @classmethod
    async def create_many(cls, count: int, *, session: AsyncSession, **overrides: Any) -> list[T]:
        """Alias for ``batch()`` — creates and persists *count* instances."""
        return await cls.batch(count, session=session, **overrides)
