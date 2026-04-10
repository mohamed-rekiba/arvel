"""Activity log — lightweight user-facing event recording.

Provides a fluent API for logging activities and querying them by subject
or causer.
"""

import arvel.activity.migration as _migration  # noqa: F401 — registers framework migration
from arvel.activity.entry import ActivityEntry
from arvel.activity.recorder import ActivityRecorder, activity

__all__ = ["ActivityEntry", "ActivityRecorder", "activity"]
