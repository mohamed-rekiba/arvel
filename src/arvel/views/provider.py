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
            factory = ViewFactory(ViewSettings().paths)  # auto-loads + validates config("view")
            # Ship the pagination link templates so paginator.links() works out of the box.
            from pathlib import Path

            import arvel.pagination

            views_dir = Path(arvel.pagination.__file__).parent / "views"
            factory.add_namespace("pagination", str(views_dir))
            # provider-registered namespaces (load_views_from) recorded before the
            # factory materialized; later registrations apply directly via the verb
            namespaces: dict[str, str] = self.app.registry("views.namespaces", dict)
            for name, path in namespaces.items():
                factory.add_namespace(name, path)
            return factory

        self.app.singleton("view", make_view)

    def boot(self) -> None:
        """No-op."""
