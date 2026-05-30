"""i18n subsystem — Translator + helpers + Python-file loader."""

from __future__ import annotations

from arvel.i18n.exceptions import (
    TranslationFileMalformedError,
    TranslationFileMissingError,
)
from arvel.i18n.helpers import t
from arvel.i18n.loader import JsonFileLoader, PythonFileLoader, TranslationLoader
from arvel.i18n.translator import Translator

__all__ = [
    "JsonFileLoader",
    "PythonFileLoader",
    "TranslationFileMalformedError",
    "TranslationFileMissingError",
    "TranslationLoader",
    "Translator",
    "t",
]
