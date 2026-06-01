"""ImageServiceProvider — wires arvel-image into an Arvel app.

Two duties:

1. ``register()`` — bind :class:`PathGenerator` (defaults to
   :class:`DefaultPathGenerator`) and :class:`ConversionRunner` as
   container singletons so application code can resolve them, and
   third-party packages can override the bindings if they want a
   different layout or queue-driven runner.
2. ``boot()`` — register ``create_media_table`` as a publishable
   migration so consumers can stamp it into ``database/migrations/``
   with ``arvel vendor:publish --tag=arvel-image``.

The image-manipulation API (:class:`arvel_image.Image`) is standalone —
apps that only transform bytes don't need the provider at all.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from arvel.providers.service_provider import ServiceProvider

from arvel_image.media import (
    ConversionRunner,
    DefaultPathGenerator,
    PathGenerator,
)


class ImageServiceProvider(ServiceProvider):
    """Boot arvel-image inside an Arvel application."""

    def register(self) -> None:
        """Bind the default :class:`PathGenerator` and a shared
        :class:`ConversionRunner` instance.

        Container is singleton-scoped: every resolution returns the same
        instance, so consumers can swap implementations app-wide by
        overriding the binding before the first resolve.
        """
        # ``Container.singleton(abstract: type[T], ...)`` — strict mypy
        # rejects ``Protocol`` types here, but ``PathGenerator`` is the
        # canonical PathGenerator binding key. Carry it through
        # an ``Any``-typed local to bypass the strict-mode check.
        path_generator_key: Any = PathGenerator
        self.container.singleton(path_generator_key, DefaultPathGenerator)
        self.container.singleton(ConversionRunner, ConversionRunner)

    async def boot(self) -> None:
        from arvel_image import migrations as image_migrations  # noqa: PLC0415

        stub = Path(image_migrations.__file__).parent / "create_media_table.py"
        self.publishes(
            {stub: "database/migrations"},
            tag="arvel-image",
            is_migrations=True,
        )
