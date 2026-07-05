"""FeatureServiceProvider — binds ``features`` (the FeatureManager) for Pennant-style flags."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.features import FeatureManager
from arvel.kernel.service_provider import ServiceProvider

if TYPE_CHECKING:
    from arvel.contracts import Container


class FeatureServiceProvider(ServiceProvider):
    def register(self) -> None:
        def make_features(app: Container) -> FeatureManager:
            return FeatureManager(app)

        self.app.singleton("features", make_features)
