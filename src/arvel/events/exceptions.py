"""Event-specific exceptions."""

from __future__ import annotations


class EventError(Exception):
    """Base exception for the events package."""


class EventDispatchError(EventError):
    """A listener raised during sync dispatch."""

    def __init__(self, message: str, *, listener_class: type, cause: Exception) -> None:
        super().__init__(message)
        self.listener_class = listener_class
        self.cause = cause


class ListenerDiscoveryError(EventError):
    """Failed to discover or validate a listener file."""

    def __init__(self, message: str, *, module_path: str) -> None:
        super().__init__(message)
        self.module_path = module_path
