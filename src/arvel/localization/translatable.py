"""Translatable model attributes.

A translatable attribute is stored as a JSON object ``{locale: value}`` (back it with a ``jsonb``
column) and **read as the current locale's value**, falling back to the configured default locale.
Declare it as a cast::

    from arvel.localization import HasTranslations, Translatable

    class Product(HasTranslations, Model):
        __casts__ = {"name": Translatable(), "description": Translatable()}

Set the whole map (``product.name = {"en": "Phone", "fr": "Téléphone"}``) or one locale at a time via
``product.set_translation("name", "fr", "Téléphone")``. Reading ``product.name`` returns the string for
``current_locale`` (set per request by ``LocaleMiddleware``).
"""

from __future__ import annotations

import json
from typing import Any, cast


def _load(value: Any) -> dict[str, Any]:
    """The stored value as a ``{locale: value}`` dict (it round-trips as a JSON string on sqlite, a
    dict on Postgres jsonb)."""
    if isinstance(value, str):
        return json.loads(value) if value else {}
    return dict(value) if value else {}


class Translatable:
    """A custom cast: DB JSON object ↔ the current locale's value."""

    def __init__(self, fallback: str = "en") -> None:
        self._fallback = fallback

    def get(self, model: Any, key: str, value: Any, attributes: dict[str, Any]) -> Any:
        from arvel.localization import current_locale

        data = _load(value)
        if not data:
            return None
        locale = current_locale.get()
        if locale in data:
            return data[locale]
        if self._fallback in data:
            return data[self._fallback]
        return next(iter(data.values()))

    def set(self, model: Any, key: str, value: Any, attributes: dict[str, Any]) -> Any:
        """Store the ``{locale: value}`` map as a dict — back the attribute with a ``jsonb``/JSON
        column and SQLAlchemy serializes it once (a pre-stringified value would double-encode and
        break ``->>`` / ``json_extract`` lookups)."""
        from arvel.localization import current_locale

        if isinstance(value, dict):
            return cast("dict[str, Any]", value)
        # a bare string sets the current locale, preserving the other translations
        data: dict[str, Any] = _load(attributes.get(key))
        data[current_locale.get()] = value
        return data


class HasTranslations:
    """Mixin adding explicit per-locale helpers to a model whose attributes use :class:`Translatable`.

    Duck-typed on the model's ``_attributes`` (no import of the database layer), so it composes with any
    arvel ``Model``: ``class Product(HasTranslations, Model)``.
    """

    _attributes: dict[str, Any]

    def set_translation(self, key: str, locale: str, value: str) -> HasTranslations:
        data = _load(self._attributes.get(key))
        data[locale] = value
        # store the dict, not json.dumps(...) — a pre-stringified value double-encodes on jsonb
        # and breaks ->>/json_extract lookups (must agree with Translatable.set)
        self._attributes[key] = data
        return self

    def get_translation(self, key: str, locale: str) -> Any:
        return _load(self._attributes.get(key)).get(locale)

    def translations(self, key: str) -> dict[str, Any]:
        return _load(self._attributes.get(key))
