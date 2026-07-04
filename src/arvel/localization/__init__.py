"""arvel.localization — Translator (``contracts.Translator``) + helpers.

Core: file/dict lookup, ``{placeholder}``/``:placeholder`` replacement, and
simple pipe-form pluralization. The ``[i18n]`` tier uses **Babel** for correct
CLDR plural categories (zero/one/two/few/many/other) — mandatory, not hand-rolled
(G4). Grounded in knowledge/port/21-localization.md.
"""

from __future__ import annotations

import contextvars
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

# translatable.py imports current_locale lazily (inside methods), so this top-level import is safe
from arvel.localization.translatable import HasTranslations, Translatable

current_locale: contextvars.ContextVar[str] = contextvars.ContextVar("arvel_locale", default="en")


def load_translations(lang_dir: Path | str) -> dict[str, dict[str, Any]]:
    """Load translations from a ``lang/`` tree.

    ``lang/<code>.json`` becomes flat short-keys for ``<code>``; ``lang/<code>/<group>.json``
    becomes a grouped namespace addressed as ``<group>.<key>``.
    """
    directory = Path(lang_dir)
    result: dict[str, dict[str, Any]] = {}
    if not directory.exists():
        return result
    for entry in sorted(directory.iterdir()):
        if entry.is_file() and entry.suffix == ".json":
            result.setdefault(entry.stem, {}).update(json.loads(entry.read_text()))
        elif entry.is_dir():
            for group in sorted(entry.glob("*.json")):
                result.setdefault(entry.name, {})[group.stem] = json.loads(group.read_text())
    return result


_CLDR_ORDER = ("zero", "one", "two", "few", "many", "other")


def plural_category(locale: str, n: int) -> str:
    """The CLDR plural category for ``n`` in ``locale`` (Babel when installed)."""
    try:
        import babel
    except ImportError:
        return "one" if n == 1 else "other"
    locale_cls: Any = babel.Locale  # babel ships no stubs — funnel through Any here
    return str(locale_cls.parse(locale).plural_form(n))


class Translator:
    """Key lookup + placeholder replacement + pluralization."""

    def __init__(
        self, translations: Mapping[str, Any] | None = None, *, fallback: str = "en"
    ) -> None:
        self._translations: dict[str, Any] = dict(translations) if translations else {}
        self._namespaces: dict[str, dict[str, Any]] = {}  # name -> {locale -> data}
        self.fallback = fallback

    def add(self, locale: str, data: Mapping[str, Any]) -> None:
        # one level deep, so a later source can override individual keys without dropping the rest
        bucket = self._translations.setdefault(locale, {})
        for key, value in data.items():
            existing = bucket.get(key)
            if isinstance(existing, dict) and isinstance(value, Mapping):
                bucket[key] = {**existing, **value}
            else:
                bucket[key] = value

    def load(self, lang_dir: Path | str) -> Translator:
        """Populate from a ``lang/`` directory (see :func:`load_translations`)."""
        for locale, data in load_translations(lang_dir).items():
            self.add(locale, data)
        return self

    def add_namespace(self, name: str, lang_dir: Path | str) -> Translator:
        """Register a package's ``lang/`` dir under ``name``; address it as ``name::group.key``.

        This is what backs ``ServiceProvider.load_translations_from(path, namespace)`` — a
        package ships its own translations without colliding with the app's keys.
        """
        store = self._namespaces.setdefault(name, {})
        for locale, data in load_translations(lang_dir).items():
            store.setdefault(locale, {}).update(data)
        return self

    def get(
        self, key: str, replace: Mapping[str, Any] | None = None, locale: str | None = None
    ) -> str:
        loc = locale or current_locale.get()
        line = self._lookup(key, loc) or self._lookup(key, self.fallback) or key
        return self._replace(line, replace or {})

    def choice(
        self, key: str, n: int, replace: Mapping[str, Any] | None = None, locale: str | None = None
    ) -> str:
        loc = locale or current_locale.get()
        line = self._lookup(key, loc) or self._lookup(key, self.fallback) or key
        segment = self._plural(line, n, loc)
        return self._replace(segment, {"count": n, "n": n, **(replace or {})})

    def get_locale(self) -> str:
        return current_locale.get()

    def set_locale(self, locale: str) -> None:
        current_locale.set(locale)

    def _lookup(self, key: str, locale: str) -> str | None:
        if "::" in key:  # pkg::group.key — resolve within the package's namespace
            ns, _, rest = key.partition("::")
            store = self._namespaces.get(ns)
            return self._lookup_in(store.get(locale) if store else None, rest)
        return self._lookup_in(self._translations.get(locale), key)

    @staticmethod
    def _lookup_in(raw: Any, key: str) -> str | None:
        if not isinstance(raw, dict):
            return None
        data = cast("dict[str, Any]", raw)
        flat = data.get(key)  # JSON short-key style
        if isinstance(flat, str):
            return flat
        node: Any = data
        for part in key.split("."):
            if isinstance(node, dict) and part in node:
                node = cast("dict[str, Any]", node)[part]
            else:
                return None
        return node if isinstance(node, str) else None

    def _replace(self, line: str, replace: Mapping[str, Any]) -> str:
        for k, v in replace.items():
            line = line.replace("{" + k + "}", str(v)).replace(":" + k, str(v))
        return line

    def _plural(self, line: str, n: int, locale: str) -> str:
        segments = [s.strip() for s in line.split("|")]
        if len(segments) == 1:
            return segments[0]
        category = plural_category(locale, n)
        if len(segments) == 2:
            return segments[0] if category == "one" else segments[1]
        wanted = _CLDR_ORDER.index(category) if category in _CLDR_ORDER else len(segments) - 1
        return segments[min(wanted, len(segments) - 1)]


_DEFAULT = Translator()


def _translator() -> Translator:
    from arvel.kernel.globals import app, has_application

    if has_application() and app().bound("translator"):
        return cast("Translator", app().make("translator"))
    return _DEFAULT


def __(key: str, **replace: Any) -> str:
    return _translator().get(key, replace)


def trans(key: str, **replace: Any) -> str:
    return _translator().get(key, replace)


def trans_choice(key: str, n: int, **replace: Any) -> str:
    return _translator().choice(key, n, replace)


__all__ = [
    "HasTranslations",
    "Translatable",
    "Translator",
    "__",
    "current_locale",
    "load_translations",
    "plural_category",
    "trans",
    "trans_choice",
]
