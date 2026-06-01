"""Envelope dataclass — email addressing and metadata."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Envelope:
    """From/to/subject and optional addressing fields for a mail message."""

    from_address: str
    to: list[str]
    subject: str
    cc: list[str] = field(default_factory=list[str])
    bcc: list[str] = field(default_factory=list[str])
    reply_to: str | None = None
    tags: list[str] = field(default_factory=list[str])


__all__ = ["Envelope"]
