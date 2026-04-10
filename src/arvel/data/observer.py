"""Model lifecycle observer system.

Observers register for model classes (or model name strings for
cross-module decoupling). Priority-based ordering, transaction-bound
execution. ``ModelObserver[T]`` is generic — subclasses parameterize
with the model type for typed lifecycle hooks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from arvel.data.model import ArvelModel

_VALID_EVENTS = frozenset(
    {
        "saving",
        "saved",
        "creating",
        "created",
        "updating",
        "updated",
        "deleting",
        "deleted",
        "force_deleting",
        "force_deleted",
        "restoring",
        "restored",
    }
)

_PRE_EVENTS = frozenset(
    {
        "saving",
        "creating",
        "updating",
        "deleting",
        "force_deleting",
        "restoring",
    }
)


class ModelObserver[T: "ArvelModel"]:
    """Base class for model lifecycle observers.

    Parameterize with the model type for typed hooks::

        class UserObserver(ModelObserver[User]):
            async def creating(self, instance: User) -> bool: ...

    Using ``ModelObserver`` without a type parameter falls back to
    ``Any`` (backward compatible).

    Override any hook method. ``creating``, ``updating``, and ``deleting``
    can return ``False`` to abort the operation.
    """

    async def saving(self, instance: T) -> bool:
        return True

    async def saved(self, instance: T) -> None:
        pass

    async def creating(self, instance: T) -> bool:
        return True

    async def created(self, instance: T) -> None:
        pass

    async def updating(self, instance: T) -> bool:
        return True

    async def updated(self, instance: T) -> None:
        pass

    async def deleting(self, instance: T) -> bool:
        return True

    async def deleted(self, instance: T) -> None:
        pass

    async def force_deleting(self, instance: T) -> bool:
        return True

    async def force_deleted(self, instance: T) -> None:
        pass

    async def restoring(self, instance: T) -> bool:
        return True

    async def restored(self, instance: T) -> None:
        pass


class ObserverRegistry:
    """Stores and dispatches model lifecycle observers.

    Observers can be registered by model class or by model name string
    (for cross-module decoupling). Multiple observers per model execute
    in priority order (lower = earlier).
    """

    def __init__(self) -> None:
        self._observers: dict[str, list[tuple[int, ModelObserver[Any]]]] = {}

    def _key(self, model: type[ArvelModel] | str) -> str:
        if isinstance(model, str):
            return model
        return model.__name__

    def register(
        self,
        model: type[ArvelModel] | str,
        observer: ModelObserver[Any],
        *,
        priority: int = 50,
    ) -> None:
        key = self._key(model)
        if key not in self._observers:
            self._observers[key] = []
        self._observers[key].append((priority, observer))
        self._observers[key].sort(key=lambda x: x[0])

    def _get_observers(self, model: type[ArvelModel]) -> list[ModelObserver[Any]]:
        key = model.__name__
        entries = self._observers.get(key, [])
        return [obs for _, obs in entries]

    async def dispatch(
        self,
        event: str,
        model_cls: type[ArvelModel],
        instance: ArvelModel,
    ) -> bool:
        """Dispatch a lifecycle event to all registered observers.

        For pre-events (creating, updating, deleting, etc.): returns
        False if any observer returns False.
        """
        if event not in _VALID_EVENTS:
            msg = f"Invalid observer event: {event!r}"
            raise ValueError(msg)
        observers = self._get_observers(model_cls)
        for obs in observers:
            handler = getattr(obs, event, None)
            if handler is None:
                continue
            result = await handler(instance)
            if event in _PRE_EVENTS and result is False:
                return False
        return True
