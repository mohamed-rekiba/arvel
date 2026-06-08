"""Translator service — looks up + substitutes translations against the current locale."""

from __future__ import annotations

from collections.abc import Mapping

from arvel.i18n.exceptions import TranslationFileMissingError
from arvel.i18n.loader import TranslationLoader, TranslationValue
from arvel.i18n.pluralisation import select_plural_variant


class Translator:
    """Looks up keys like ``messages.welcome.greeting`` against ``resources/lang/``."""

    def __init__(
        self,
        loader: TranslationLoader,
        *,
        default_locale: str = "en",
        fallback_locale: str | None = None,
    ) -> None:
        self._loader = loader
        self._locale = default_locale
        self._fallback = fallback_locale
        # Cache: (locale, namespace) -> dict
        self._cache: dict[tuple[str, str], dict[str, TranslationValue]] = {}

    # ── State ────────────────────────────────────────────────────────────
    def set_locale(self, locale: str) -> None:
        self._locale = locale

    def get_locale(self) -> str:
        return self._locale

    def set_fallback(self, locale: str) -> None:
        self._fallback = locale

    def reload(self) -> None:
        """Drop the in-process namespace cache so next lookup re-reads files."""
        self._cache.clear()

    def cached_namespaces(self) -> frozenset[tuple[str, str]]:
        """Return the ``(locale, namespace)`` pairs currently in the cache.

        Exposes the caching invariant to callers and tests
        without leaking the underlying mapping.
        """
        return frozenset(self._cache)

    # ── Lookup ───────────────────────────────────────────────────────────
    def get(
        self,
        key: str,
        replace: Mapping[str, object] | None = None,
        locale: str | None = None,
    ) -> str:
        replace = replace or {}
        loc = locale or self._locale
        raw = self._lookup(key, loc)
        if raw is None and self._fallback and self._fallback != loc:
            raw = self._lookup(key, self._fallback)
        if raw is None:
            return key
        if not isinstance(raw, str):
            # Hit on a nested dict — return the key (no string at this path)
            return key
        return _substitute(raw, replace)

    def choice(
        self,
        key: str,
        count: int,
        replace: Mapping[str, object] | None = None,
        locale: str | None = None,
    ) -> str:
        replace = replace or {}
        loc = locale or self._locale
        raw = self.get(key, locale=loc)
        # If the key didn't resolve, `get` returned the key verbatim. We pass
        # that through pluralisation harmlessly: count=N -> still the key.
        return select_plural_variant(raw, count=count, replace=replace, locale=loc)

    # ── Internal ─────────────────────────────────────────────────────────
    def _lookup(self, key: str, locale: str) -> TranslationValue | None:
        if "." not in key:
            return None
        namespace, _, rest = key.partition(".")
        try:
            data = self._load(locale, namespace)
        except TranslationFileMissingError:
            return None
        return _traverse(data, rest)

    def _load(self, locale: str, namespace: str) -> dict[str, TranslationValue]:
        cache_key = (locale, namespace)
        if cache_key not in self._cache:
            self._cache[cache_key] = self._loader.load(locale, namespace)
        return self._cache[cache_key]


def _traverse(data: dict[str, TranslationValue], path: str) -> TranslationValue | None:
    """Walk dotted path through nested dicts."""
    current: TranslationValue = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _substitute(text: str, replace: Mapping[str, object]) -> str:
    """003: pure string replacement; never eval'd."""
    result = text
    for key, value in replace.items():
        result = result.replace(f":{key}", str(value))
        result = result.replace("{" + key + "}", str(value))
    return result


__all__ = ["Translator"]
