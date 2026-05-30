"""i18n-specific exceptions."""

from __future__ import annotations


class TranslationError(Exception):
    """Base class."""


class TranslationFileMissingError(TranslationError):
    """The locale+namespace file does not exist."""

    def __init__(self, locale: str, namespace: str) -> None:
        super().__init__(f"translation file missing: locale={locale!r} namespace={namespace!r}")
        self.locale = locale
        self.namespace = namespace


class TranslationFileMalformedError(TranslationError):
    """The translation file exists but does not expose a `translations: dict` export."""


__all__ = [
    "TranslationError",
    "TranslationFileMalformedError",
    "TranslationFileMissingError",
]
