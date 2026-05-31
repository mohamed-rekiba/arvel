"""Reusable model mixins for the Arvel database layer.

``TranslatableMixin`` — JSONB i18n field helpers (get_translation / set_translation).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

__all__ = ["PublishableMixin", "TranslatableMixin", "parse_trashed_mode"]


def parse_trashed_mode(request_or_value: Any) -> Literal["without", "with", "only"]:
    """Parse a ``?trashed=`` query parameter into a typed mode string.

    Accepts either a Starlette ``Request`` (reads ``request.query_params``) or
    a raw string value::

        mode = parse_trashed_mode(request)           # from HTTP request
        mode = parse_trashed_mode("only")            # from explicit value
    """
    if hasattr(request_or_value, "query_params"):
        value = request_or_value.query_params.get("trashed", "without")
    else:
        value = str(request_or_value)
    if value == "with":
        return "with"
    if value == "only":
        return "only"
    return "without"


class PublishableMixin:
    """Helpers for managing ``published_at`` timestamps on publishable models."""

    @staticmethod
    def resolve_published_at(status: str, published_at: datetime | None) -> datetime | None:
        """Return the publish timestamp for a given status transition.

        If ``status != "published"``, returns ``None`` (clears the timestamp).
        If status is ``"published"`` and ``published_at`` is provided, uses it.
        Otherwise defaults to ``now(UTC)``.
        """
        if status != "published":
            return None
        return published_at or datetime.now(UTC)


class TranslatableMixin:
    """Helpers for reading and writing JSONB i18n fields.

    Models with multilingual JSONB columns (e.g. ``name: dict[str, Any]``) inherit
    this mixin to get locale-aware get/set without boilerplate::

        class Category(TranslatableMixin, Model):
            name: dict[str, Any] = jsonb(default=dict)

        category.get_translation("name", "ar")   # → Arabic name or falls back to "en"
        category.set_translation("name", "fr", "Électronique")
    """

    def get_translation(self, field: str, locale: str) -> str:
        """Return the ``locale`` value of ``field``, falling back to ``'en'``."""
        data: dict[str, str] = getattr(self, field, None) or {}
        if locale in data:
            return data[locale]
        return data.get("en", "")

    def set_translation(self, field: str, locale: str, value: str) -> None:
        """Patch a single locale key in the JSONB field."""
        data: dict[str, str] = dict(getattr(self, field, None) or {})
        data[locale] = value
        setattr(self, field, data)

    @staticmethod
    def translate_dict(data: dict[str, str], locale: str) -> str:
        """Resolve a translation from a plain dict (not a model instance).

        Falls back to ``"en"`` when the requested locale is absent::

            name = TranslatableMixin.translate_dict({"en": "Chair", "ar": "كرسي"}, "ar")
        """
        if locale in data:
            return data[locale]
        return data.get("en", "")
