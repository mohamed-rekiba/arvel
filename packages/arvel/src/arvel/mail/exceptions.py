"""Mail subsystem exceptions."""

from __future__ import annotations


class MailException(Exception):
    """Base exception for all mail errors."""


__all__ = ["MailException"]
