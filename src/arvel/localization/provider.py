"""LocalizationServiceProvider — binds the ``translator`` (root of the Lang facade).

Without this binding the ``Lang`` facade can't resolve, and the bound-``translator`` paths
(localized validation messages, package translation namespaces) never activate — the module-level
``trans()``/``__()`` helpers fall back to a default ``Translator``, but ``Lang.get(...)`` raises.

On boot it loads the framework's bundled default lang files (``validation``/``auth``/``http``), then the
app's ``{base_path}/lang`` dir (which overrides them), and registers the bundled defaults as publishable
(``vendor:publish --tag=lang``) so an app can copy + edit them — Laravel ``lang:publish``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from arvel.kernel.service_provider import ServiceProvider
from arvel.localization import Translator

if TYPE_CHECKING:
    from arvel.contracts import Container

# bundled defaults: validation / auth / http
_FRAMEWORK_LANG = Path(__file__).parent / "lang"


class LocalizationServiceProvider(ServiceProvider):
    def register(self) -> None:
        def make_translator(app: Container) -> Translator:
            fallback = app.make("config").get("app.fallback_locale", "en")
            return Translator(fallback=fallback)

        self.app.singleton("translator", make_translator)
        # app.lang_dir is set by ApplicationBuilder.create() before providers register, so this
        # is the real destination, not a bare "lang" relative to the CLI's CWD
        dest = self.app.lang_dir or str(Path(self.app.base_path) / "lang")
        self.publishes({str(_FRAMEWORK_LANG): dest}, tag="lang")

    def boot(self) -> None:
        translator = self.app.make("translator")
        if _FRAMEWORK_LANG.is_dir():
            translator.load(_FRAMEWORK_LANG)
        # with_lang_dir(...) overrides the default {base_path}/lang
        app_lang = (
            Path(self.app.lang_dir) if self.app.lang_dir else Path(self.app.base_path) / "lang"
        )
        if app_lang.is_dir():  # loaded after the framework defaults, so it overrides them
            translator.load(app_lang)
