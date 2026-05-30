"""LangServiceProvider — registers Translator and binds __() / __choice() helpers.

Loader selection follows file presence:

1. ``resources/lang/*.json`` exist → :class:`JsonFileLoader`
2. ``lang/`` Python modules exist → :class:`PythonFileLoader` (legacy default)

The default locale is read from ``config/app.py`` (key ``app.locale``),
defaulting to ``"en"`` when not configured.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from arvel.providers.service_provider import ServiceProvider

if TYPE_CHECKING:
    from arvel.application import Application


def _resolve_base_path(app: Application) -> Path:
    """Return the app's base path, callable or attribute, fallback to cwd."""
    base_attr: object = getattr(app, "base_path", None)
    base_value: object = base_attr() if callable(base_attr) else base_attr
    if isinstance(base_value, Path):
        return base_value
    if isinstance(base_value, str):
        return Path(base_value)
    return Path()


def _resolve_default_locale() -> str:
    """Read the default locale from config/app.py (key ``app.locale``)."""
    from arvel.config import config

    return config("app.locale", "en")


def _has_json_catalogs(base: Path) -> bool:
    """Return True when ``resources/lang/*.json`` files exist under ``base``."""
    lang_dir = base / "resources" / "lang"
    return lang_dir.is_dir() and any(lang_dir.glob("*.json"))


class LangServiceProvider(ServiceProvider):
    """Wires the Translator service and module-level __() helper."""

    def register(self) -> None:
        from arvel.i18n import JsonFileLoader, PythonFileLoader, Translator
        from arvel.i18n.helpers import bind_translator

        c = self.app.container
        base = _resolve_base_path(self.app)
        default_locale = _resolve_default_locale()

        loader: JsonFileLoader | PythonFileLoader
        if _has_json_catalogs(base):
            loader = JsonFileLoader(base_path=base)
        else:
            loader = PythonFileLoader(base_path=base)

        translator = Translator(
            loader=loader,
            default_locale=default_locale,
            fallback_locale=default_locale,
        )
        c.instance(Translator, translator)
        bind_translator(translator)

    async def boot(self) -> None:
        pass


__all__ = ["LangServiceProvider"]
