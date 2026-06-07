"""Envelope dataclass — email addressing and metadata."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(kw_only=True)
class Envelope:
    """From/to/subject and optional addressing fields for a mail message.

    Leave ``from_address``/``from_name`` unset to inherit the global ``mail.from``
    config — the Mailer fills them in at render time, matching Laravel.
    """

    to: list[str]
    subject: str
    from_address: str = ""
    from_name: str | None = None
    cc: list[str] = field(default_factory=list[str])
    bcc: list[str] = field(default_factory=list[str])
    reply_to: str | None = None
    tags: list[str] = field(default_factory=list[str])


__all__ = ["Envelope"]
