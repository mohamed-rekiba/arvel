"""RenderedMail — fully rendered email ready for driver delivery."""

from __future__ import annotations

from dataclasses import dataclass, field

from arvel.mail.attachment import Attachment
from arvel.mail.envelope import Envelope


@dataclass
class RenderedMail:
    """A rendered email message: envelope + pre-rendered body text (and optional HTML)."""

    envelope: Envelope
    body_text: str
    body_html: str | None
    attachments: list[Attachment] = field(default_factory=list[Attachment])


__all__ = ["RenderedMail"]
