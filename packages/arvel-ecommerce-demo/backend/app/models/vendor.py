"""Vendor model — seller entity behind product catalog."""

from __future__ import annotations

import uuid
from datetime import datetime as _datetime

from arvel.database import (
    Model,
    SoftDeletes,
    Timestamps,
    TranslatableMixin,
    datetime,
    enum,
    string,
    text,
    uuid_id,
)


class Vendor(TranslatableMixin, Model, Timestamps, SoftDeletes):
    __tablename__ = "vendors"

    id: uuid.UUID = uuid_id(init=False)
    name: str = string(200, default="")
    slug: str = string(200, unique=True, default="")
    description: str | None = text(nullable=True, default=None)
    status: str = enum(["draft", "published"], name="vendors_status", default="published")
    published_at: _datetime | None = datetime(nullable=True, default=None)


__all__ = ["Vendor"]
