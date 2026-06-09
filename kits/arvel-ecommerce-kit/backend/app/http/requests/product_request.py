"""Declarative FK validation for admin product create/update.

Existence is delegated to the framework Validator (``Rule.exists``) instead of
the imperative ``.count()`` lookups that used to live in ProductService.

Two deliberate choices:

- Runs *after* the controller's ``require_permission`` guard. The admin route
  group has no auth middleware, and the framework's auto-wired FormRequest runs
  validation before ``authorize()`` — so auto-wiring would let an
  unauthenticated caller probe whether a category/vendor id exists. Guard-first
  keeps that closed (OWASP A01/A07).
- str→UUID coercion stays here. It's request-layer input parsing, and it lets
  ``Rule.exists`` bind a real uuid to the uuid PK column — a raw string trips
  Postgres' ``uuid = text``. Blank/absent normalizes to ``None`` (nullable FK).
"""

from __future__ import annotations

import uuid
from typing import Any

from arvel.http.exceptions import ValidationException
from arvel.validation import Rule, Validator

_FK_TABLES: tuple[tuple[str, str], ...] = (
    ("category_id", "categories"),
    ("vendor_id", "vendors"),
)


async def validate_product_fks(data: dict[str, Any]) -> None:
    """Coerce + verify category_id/vendor_id in place. Raises on bad input.

    Only touches keys present in ``data`` (update sends partial payloads).
    """
    rules: dict[str, str | list[str]] = {}
    for field, table in _FK_TABLES:
        if field not in data:
            continue
        raw = data[field]
        if not raw:
            data[field] = None
            continue
        try:
            data[field] = uuid.UUID(str(raw))
        except ValueError as exc:
            raise ValidationException(
                "Validation failed.",
                details=[{"field": field, "issue": "must be a valid UUID"}],
            ) from exc
        rules[field] = Rule.exists(table, "id")

    if not rules:
        return
    details = await Validator(data).validate(rules)
    if details:
        raise ValidationException("Validation failed.", details=details)
