"""Shared marker mixin for the e-commerce domain models.

``TranslatableMixin`` re-exported from the framework so domain modules can pull
both from a single location. Real media uses ``arvel_image.HasMedia`` directly.
"""

from __future__ import annotations

from arvel.database import TranslatableMixin


class BaseModelMixin:
    """Mixin marker for domain models.

    Intentionally empty — framework ActiveRecord methods (delete, restore,
    scope_active) must not be shadowed by sync implementations here.
    """


__all__ = ["BaseModelMixin", "TranslatableMixin"]
