"""Search module exceptions — typed errors for search engine failures."""

from __future__ import annotations

from arvel.foundation.exceptions import ArvelError


class SearchEngineError(ArvelError):
    """Base error for all search engine failures.

    Attributes:
        engine: Name of the driver that raised the error (e.g., "meilisearch").
    """

    def __init__(self, message: str, *, engine: str) -> None:
        super().__init__(message)
        self.engine = engine


class SearchIndexNotFoundError(SearchEngineError):
    """Raised when an operation targets a non-existent index.

    Attributes:
        index: Name of the missing index.
    """

    def __init__(self, message: str, *, engine: str, index: str) -> None:
        super().__init__(message, engine=engine)
        self.index = index


class SearchConnectionError(SearchEngineError):
    """Raised when the driver can't reach the search engine.

    Attributes:
        url: Connection URL that failed (credentials stripped).
    """

    def __init__(self, message: str, *, engine: str, url: str) -> None:
        super().__init__(message, engine=engine)
        self.url = url


class SearchConfigurationError(SearchEngineError):
    """Raised when the driver is misconfigured (e.g., missing SDK).

    Attributes:
        detail: Explanation of what's wrong.
    """

    def __init__(self, message: str, *, engine: str, detail: str) -> None:
        super().__init__(message, engine=engine)
        self.detail = detail
