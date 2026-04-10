"""Media library — model-associated file management with collections, conversions, and events.

Feature-complete media library inspired by Spatie Laravel Media Library:
https://spatie.be/docs/laravel-medialibrary/v11/introduction
"""

from arvel.media.adder import MediaAdder as MediaAdder
from arvel.media.config import MediaSettings as MediaSettings
from arvel.media.contracts import MediaContract as MediaContract
from arvel.media.events import CollectionHasBeenCleared as CollectionHasBeenCleared
from arvel.media.events import ConversionHasBeenCompleted as ConversionHasBeenCompleted
from arvel.media.events import ConversionWillStart as ConversionWillStart
from arvel.media.events import MediaEvent as MediaEvent
from arvel.media.events import MediaHasBeenAdded as MediaHasBeenAdded
from arvel.media.exceptions import MediaError as MediaError
from arvel.media.exceptions import MediaProcessingError as MediaProcessingError
from arvel.media.exceptions import MediaValidationError as MediaValidationError
from arvel.media.fakes import MediaFake as MediaFake
from arvel.media.image_processor import ImageProcessor as ImageProcessor
from arvel.media.image_processor import is_processable as is_processable
from arvel.media.manager import MediaManager as MediaManager
from arvel.media.mixins import HasMedia as HasMedia
from arvel.media.provider import MediaProvider as MediaProvider

# MediaItem is lazy-imported to avoid triggering SQLAlchemy ORM setup at
# import time. Use ``from arvel.media.models import MediaItem`` directly
# when you need the ORM model.
from arvel.media.types import Conversion as Conversion
from arvel.media.types import JsonValue as JsonValue
from arvel.media.types import Media as Media
from arvel.media.types import MediaCollection as MediaCollection
from arvel.media.types import MediaModelDict as MediaModelDict
from arvel.media.types import MediaOwner as MediaOwner
from arvel.media.types import MediaOwnerOrDict as MediaOwnerOrDict

__all__ = [
    "CollectionHasBeenCleared",
    "Conversion",
    "ConversionHasBeenCompleted",
    "ConversionWillStart",
    "HasMedia",
    "ImageProcessor",
    "JsonValue",
    "Media",
    "MediaAdder",
    "MediaCollection",
    "MediaContract",
    "MediaError",
    "MediaEvent",
    "MediaFake",
    "MediaHasBeenAdded",
    "MediaManager",
    "MediaModelDict",
    "MediaOwner",
    "MediaOwnerOrDict",
    "MediaProcessingError",
    "MediaProvider",
    "MediaSettings",
    "MediaValidationError",
    "is_processable",
]
