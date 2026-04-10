"""Mailable base class — defines the email envelope and content."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Attachment:
    """A file attachment for a mailable."""

    filename: str
    content: bytes
    content_type: str = "application/octet-stream"


@dataclass
class Mailable:
    """Base class for email messages.

    Subclass and override fields to create typed mailables:

        class WelcomeEmail(Mailable):
            subject: str = "Welcome to Arvel"
            template: str = "welcome.html"
    """

    to: list[str] = field(default_factory=list)
    cc: list[str] = field(default_factory=list)
    bcc: list[str] = field(default_factory=list)
    subject: str = ""
    body: str = ""
    html_body: str = ""
    template: str = ""
    context: dict[str, object] = field(default_factory=dict)
    attachments: list[Attachment] = field(default_factory=list)
