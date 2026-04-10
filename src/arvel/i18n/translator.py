"""Core translator — loads JSON lang files and resolves keys."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


class Translator:
    """Thread-safe translator with per-module, per-locale dictionaries.

    Key format: ``"module.key"`` — the module prefix maps to a loaded
    module name and the key suffix indexes into the translation dict.
    """

    def __init__(
        self,
        *,
        default_locale: str = "en",
        fallback_locale: str = "en",
    ) -> None:
        self._default_locale = default_locale
        self._fallback_locale = fallback_locale
        self._catalog: dict[str, dict[str, dict[str, str]]] = {}

    @property
    def default_locale(self) -> str:
        return self._default_locale

    @default_locale.setter
    def default_locale(self, value: str) -> None:
        self._default_locale = value

    def load_module(self, module_name: str, lang_dir: Path) -> None:
        """Load all ``{locale}.json`` files from *lang_dir* into the catalog."""
        if not lang_dir.is_dir():
            return
        for path in lang_dir.glob("*.json"):
            locale = path.stem
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
            self._catalog.setdefault(module_name, {})[locale] = data

    def get(
        self,
        key: str,
        *,
        locale: str | None = None,
        **params: Any,
    ) -> str:
        """Resolve *key* (``module.subkey``) to a translated string.

        Returns the key itself when the translation is missing (Laravel convention).
        """
        parts = key.split(".", 1)
        if len(parts) != 2:
            return key

        module, subkey = parts
        active_locale = locale or self._default_locale

        text = self._resolve(module, subkey, active_locale)
        if text is None and active_locale != self._fallback_locale:
            text = self._resolve(module, subkey, self._fallback_locale)
        if text is None:
            return key

        if params:
            try:
                return text.format(**params)
            except KeyError:
                return text
        return text

    def _resolve(self, module: str, subkey: str, locale: str) -> str | None:
        module_data = self._catalog.get(module)
        if module_data is None:
            return None
        locale_data = module_data.get(locale)
        if locale_data is None:
            return None
        return locale_data.get(subkey)
