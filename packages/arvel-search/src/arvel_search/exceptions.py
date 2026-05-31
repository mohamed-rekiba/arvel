"""Search exception hierarchy."""

from __future__ import annotations


class SearchError(Exception):
    """Base class for all search failures."""


class SearchEngineNotConfigured(SearchError):
    """Raised when a search query runs but no engine has been bound.

    Means ``SearchServiceProvider`` wasn't registered — not a runtime null deref.
    """

    def __init__(self) -> None:
        super().__init__(
            "No search engine is configured. Register SearchServiceProvider in "
            "bootstrap/providers.py (or bind a SearchManager) before calling search()."
        )


class UnknownSearchDriverError(SearchError):
    """Raised when ``SEARCH_DRIVER`` names a driver that isn't registered."""

    def __init__(self, driver: str, available: list[str]) -> None:
        self.driver = driver
        self.available = available
        super().__init__(
            f"Unknown search driver {driver!r}. Available: {', '.join(available) or '(none)'}."
        )


__all__ = ["SearchEngineNotConfigured", "SearchError", "UnknownSearchDriverError"]
