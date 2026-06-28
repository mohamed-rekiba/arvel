"""ViewServiceProvider — binds the Jinja2 ViewFactory (auto-discovered)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.kernel import Settings
from arvel.kernel.service_provider import ServiceProvider
from arvel.views import ViewFactory

if TYPE_CHECKING:
    from arvel.kernel import Application


class ViewSettings(Settings):
    """Typed, validated view over the ``view`` config section (DR-0016)."""

    __config_key__ = "view"
    paths: str | list[str] = "resources/views"  # single root or several (ViewFactory accepts both)


class ViewServiceProvider(ServiceProvider):
    def register(self) -> None:
        def make_view(_app: Application) -> ViewFactory:
            return ViewFactory(ViewSettings().paths)  # auto-loads + validates config("view")

        self.app.singleton("view", make_view)

    def boot(self) -> None:
        """No-op."""
