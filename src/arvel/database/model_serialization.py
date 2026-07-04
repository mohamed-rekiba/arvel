"""arvel.database.model_serialization — ``SerializesModels``: ``to_dict``/``to_json`` and the
``__hidden__``/``__visible__`` visibility surface (Laravel Model serialization parity, doc 07).
"""

from __future__ import annotations

import json
from typing import Any, ClassVar, Self

from arvel.database.model_casts import json_default


class SerializesModels:
    """``to_dict()``/``to_json()`` (honoring ``__hidden__``/``__visible__``/``__appends__`` and
    eager-loaded relations) + ``make_hidden``/``make_visible``.

    The attribute declarations below are a mixin type stub only (see :class:`HasCasts` for why) —
    the real state lives on ``Model``."""

    __hidden__: ClassVar[list[str]]
    __visible__: ClassVar[list[str]]
    __appends__: ClassVar[list[str]]
    _attributes: dict[str, Any]
    _extra_hidden: set[str]
    _extra_visible: set[str]
    _relations: dict[str, Any]

    def _cast_get(self, key: str, value: Any) -> Any:  # provided by HasCasts
        raise NotImplementedError

    def make_hidden(self, *keys: str) -> Self:
        self._extra_hidden.update(keys)
        self._extra_visible.difference_update(keys)
        return self

    def make_visible(self, *keys: str) -> Self:
        """Reveal attributes for this instance — including ones in the class ``__hidden__``
        list (Laravel ``makeVisible``), not only those previously hidden via ``make_hidden``."""
        self._extra_visible.update(keys)
        self._extra_hidden.difference_update(keys)
        return self

    def to_dict(self) -> dict[str, Any]:
        data = {key: self._cast_get(key, value) for key, value in self._attributes.items()}
        for key in self.__appends__:  # computed accessors not stored as attributes
            data[key] = self._cast_get(key, None)
        if self.__visible__:
            data = {k: v for k, v in data.items() if k in self.__visible__}
        hidden = (set(self.__hidden__) | self._extra_hidden) - self._extra_visible
        for key in hidden:
            data.pop(key, None)
        # Laravel toArray parity: eager-loaded relations serialize (nested) alongside attributes —
        # a has-many/many-to-many → a list of dicts, a has-one/belongs-to → a single nested dict,
        # a null relation → None. Only LOADED relations appear (unloaded ones are not serialized).
        for name, related in self._relations.items():
            data[name] = self._relation_to_dict(related)
        return data

    @staticmethod
    def _relation_to_dict(related: Any) -> Any:
        from arvel.database.model import Model  # deferred: model.py imports this mixin

        if related is None:  # a loaded but empty has-one / belongs-to (Laravel → null)
            return None
        if isinstance(related, Model):  # has-one / belongs-to → a single nested dict
            return related.to_dict()
        # a has-many / belongs-to-many result: a list/Collection of models → a list of dicts
        return [item.to_dict() for item in related]

    def to_json(self, **kwargs: Any) -> str:
        """Serialize ``to_dict()`` to a JSON string, honoring hidden/visible/appends (D3)."""
        return json.dumps(self.to_dict(), default=json_default, **kwargs)


__all__ = ["SerializesModels"]
