"""Mailable abstract base class (ADR-038, FR-009-011)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from arvel.mail.attachment import Attachment
from arvel.mail.content import Content
from arvel.mail.envelope import Envelope


class Mailable(ABC):
    """Base class for all email messages.

    Subclasses implement ``envelope()`` and ``content()``.
    ``attachments()`` returns an empty list by default.
    """

    @abstractmethod
    def envelope(self) -> Envelope:
        """Return the From/To/Subject and addressing metadata."""

    @abstractmethod
    def content(self) -> Content:
        """Return the body. Supply an inline string or a Jinja2 template name
        for either or both of HTML and plain text. See :class:`Content` for
        the validation rules.
        """

    def attachments(self) -> list[Attachment]:
        """Return file attachments. Default: none."""
        return []


__all__ = ["Mailable"]
