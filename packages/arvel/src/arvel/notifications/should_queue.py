"""ShouldQueue marker mixin for Notifications.

When a Notification also inherits ShouldQueue, NotificationManager.send()
dispatches it via the queue rather than sending inline. Use notify_now()
to bypass the queue regardless.
"""


class ShouldQueue:
    """Marker mixin. Inherit alongside Notification to enable queued dispatch."""


__all__ = ["ShouldQueue"]
