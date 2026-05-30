"""Container error hierarchy."""

from __future__ import annotations


class BindingResolutionError(Exception):
    """Raised when the container cannot resolve a binding."""

    def __init__(self, path: tuple[type, ...], *, reason: str = "unresolved") -> None:
        self.path = path
        self.reason = reason
        trail = " -> ".join(t.__qualname__ for t in path) if path else "<no path>"
        super().__init__(f"Cannot resolve dependency [{trail}]: {reason}.")


class CircularDependencyError(BindingResolutionError):
    """Raised when a cycle is detected during resolution."""

    def __init__(self, cycle: tuple[type, ...]) -> None:
        self.cycle = cycle
        trail = " -> ".join(t.__qualname__ for t in cycle)
        # Bypass parent __init__ to avoid double-formatting
        Exception.__init__(self, f"Circular dependency detected: {trail}.")
        self.path = cycle
        self.reason = "cycle"


class AsyncBindingError(BindingResolutionError):
    """Raised when ``make()`` (sync) is called on an async-only binding."""

    def __init__(self, abstract: type) -> None:
        self.abstract = abstract
        Exception.__init__(
            self,
            f"{abstract.__qualname__} is bound to an async factory. Use container.amake() instead.",
        )
        self.path = (abstract,)
        self.reason = "async-only"
