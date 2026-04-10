"""Internationalization (i18n) — per-module language resources.

Load JSON translation files from module ``lang/`` directories.
Use ``trans("module.key", **params)`` for localized strings.
"""

from __future__ import annotations

from arvel.i18n.translator import Translator

_default_translator: Translator | None = None


def set_translator(t: Translator | None) -> None:
    """Set the global translator instance (called at boot). Pass None to clear."""
    global _default_translator
    _default_translator = t


def get_translator() -> Translator | None:
    return _default_translator


def trans(key: str, *, locale: str | None = None, **params: object) -> str:
    """Translate a key using the global translator.

    Falls back to returning the key itself if no translator is configured
    or the key is missing.
    """
    if _default_translator is None:
        return key
    return _default_translator.get(key, locale=locale, **params)


__all__ = ["Translator", "get_translator", "set_translator", "trans"]
