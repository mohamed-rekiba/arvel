"""MediaServiceProvider — binds the Image + Video managers (auto-discovered)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.kernel.service_provider import ServiceProvider
from arvel.media import ImageManager, VideoManager

if TYPE_CHECKING:
    from arvel.contracts import Container


class MediaServiceProvider(ServiceProvider):
    def register(self) -> None:
        def make_image(_app: Container) -> ImageManager:
            return ImageManager()

        def make_video(_app: Container) -> VideoManager:
            return VideoManager()

        self.app.singleton("image", make_image)
        self.app.singleton("video", make_video)

    def boot(self) -> None:
        """No-op."""
