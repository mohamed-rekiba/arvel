"""Auditable mixin — marks a model for automatic audit trail recording."""

from __future__ import annotations

from typing import ClassVar


class Auditable:
    """Mixin for ArvelModel subclasses that enables audit tracking.

    Set ``__audit_redact__`` to a set of field names whose values should be
    replaced with ``"[REDACTED]"`` in audit entries (e.g. passwords, tokens).
    """

    __audit_redact__: ClassVar[set[str]] = set()
