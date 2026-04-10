"""Media library events — dispatched during media lifecycle operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arvel.media.types import Conversion, Media


@dataclass(frozen=True)
class MediaHasBeenAdded:
    """Fired after a file has been saved to storage and associated with a model."""

    media: Media


@dataclass(frozen=True)
class ConversionWillStart:
    """Fired right before a conversion begins processing."""

    media: Media
    conversion: Conversion


@dataclass(frozen=True)
class ConversionHasBeenCompleted:
    """Fired when a single conversion has finished processing."""

    media: Media
    conversion: Conversion


@dataclass(frozen=True)
class CollectionHasBeenCleared:
    """Fired after all media in a collection has been removed."""

    model_type: str
    model_id: int
    collection_name: str


MediaEvent = (
    MediaHasBeenAdded | ConversionWillStart | ConversionHasBeenCompleted | CollectionHasBeenCleared
)
"""Union of all media lifecycle events. Use for typed event listeners."""
