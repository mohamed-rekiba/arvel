"""Attachment dataclass — email file attachment."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Attachment:
    """An email attachment. Provide either ``path`` (file on disk) or ``data`` (bytes)."""

    name: str
    mime: str
    path: str | None = None
    data: bytes | None = None


__all__ = ["Attachment"]
