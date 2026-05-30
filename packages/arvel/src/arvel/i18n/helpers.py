"""Module-level __() / __choice() helpers and the request-aware t() helper."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.requests import Request

    from arvel.i18n.translator import Translator

_translator: Translator | None = None


def bind_translator(translator: Translator) -> None:
    """LangServiceProvider calls this on boot. Tests call it via fixture."""
    global _translator
    _translator = translator


def unbind_translator() -> None:
    global _translator
    _translator = None


def __(key: str, *, locale: str | None = None, **replace: object) -> str:
    """Look up ``key`` against the bound Translator and substitute replacements.

    ``locale`` is keyword-only so it can't collide with a placeholder
    named ``locale`` in the translation string. When ``None`` (the
    default) the Translator's current default locale is used; pass
    ``locale="es"`` for per-call overrides — typical from a request
    middleware that has just negotiated the user's locale.
    """
    if _translator is None:
        return key
    return _translator.get(key, replace=replace, locale=locale)


def __choice(key: str, count: int, *, locale: str | None = None, **replace: object) -> str:
    """Pluralise via the bound Translator using Laravel-pipe / bracket syntax.

    Accepts the same keyword-only ``locale`` override as :func:`__`.
    """
    if _translator is None:
        return key
    return _translator.choice(key, count=count, replace=replace, locale=locale)


def t(request: Request, key: str, **replace: object) -> str:
    """Look up ``key`` against the request's negotiated locale.

    Reads ``request.state.locale`` set by :class:`arvel.i18n.middleware.SetLocaleMiddleware`.
    Falls back to ``"en"`` when the middleware hasn't run or the attribute is absent.
    Concurrency-safe — never mutates the global Translator.
    """
    locale: str = getattr(request.state, "locale", "en")
    return __(key, locale=locale, **replace)


__all__ = ["__", "__choice", "bind_translator", "t", "unbind_translator"]
