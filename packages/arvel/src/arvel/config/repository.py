"""Facade-style accessor returning typed config sections from the container."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, TypeVar

from arvel.config.errors import ConfigNotRegisteredError

if TYPE_CHECKING:
    from arvel.container import Container

T = TypeVar("T")


class Config:
    """Looks up a registered ``ArvelSettings`` subclass from the bound container."""

    _container: ClassVar[Container | None] = None

    @classmethod
    def bind(cls, container: Container) -> None:
        cls._container = container

    @classmethod
    def of(cls, settings_cls: type[T]) -> T:
        if cls._container is None or not cls._container.bound(settings_cls):
            raise ConfigNotRegisteredError(settings_cls)
        return cls._container.make(settings_cls)
