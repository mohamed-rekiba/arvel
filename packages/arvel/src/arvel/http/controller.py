"""Base ``Controller`` for invokable + multi-action controllers."""

from __future__ import annotations


class Controller:
    """Marker / convenience base for HTTP controllers.

    Subclasses may be:
    - Multi-action: declare methods (``index``, ``show``, ``store``, ...) and bind
      one route per method via
      ``Route.get("/...", controller=MyController, action="index")``.
    - Invokable: declare ``async def __call__(self, ...)`` and bind via
      ``Route.get("/...", controller=MyController)``.

    All controllers are resolved via the Arvel container.
    """

    def __init__(self) -> None:
        super().__init__()
