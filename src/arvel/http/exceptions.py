"""HTTP exception hierarchy.

Typed exceptions for routing, middleware, controller, model binding,
and signed URL errors. These extend the foundation ArvelError hierarchy.
"""

from __future__ import annotations

from arvel.foundation.exceptions import ArvelError


class HttpError(ArvelError):
    """Base for all HTTP-layer framework exceptions."""


class RouteRegistrationError(HttpError):
    """Raised when route registration fails (e.g., duplicate names).

    Attributes:
        route_name: The conflicting route name.
        paths: The paths that share the name.
    """

    def __init__(
        self,
        message: str,
        *,
        route_name: str,
        paths: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.route_name = route_name
        self.paths = paths or []


class MiddlewareResolutionError(HttpError):
    """Raised when a middleware alias can't be resolved at boot time.

    Attributes:
        alias: The alias that couldn't be resolved.
        class_path: The dotted class path that failed to import.
    """

    def __init__(
        self,
        message: str,
        *,
        alias: str,
        class_path: str | None = None,
    ) -> None:
        super().__init__(message)
        self.alias = alias
        self.class_path = class_path


class HttpException(HttpError):  # noqa: N818
    """HTTP exception with a status code for response mapping.

    Attributes:
        status_code: HTTP status code.
        detail: Human-readable error detail.
    """

    def __init__(
        self,
        status_code: int,
        detail: str = "",
    ) -> None:
        super().__init__(detail or f"HTTP {status_code}")
        self.status_code = status_code
        self.detail = detail


class ModelNotFoundError(HttpException):
    """Raised when route model binding can't find the requested model.

    Returns a 404 response.
    """

    def __init__(self, model_name: str, identifier: str) -> None:
        super().__init__(404, f"{model_name} not found")
        self.model_name = model_name
        self.identifier = identifier


class InvalidSignatureError(HttpException):
    """Raised when a signed URL has an invalid or expired signature.

    Returns a 403 response.
    """

    def __init__(self, reason: str = "Invalid signature") -> None:
        super().__init__(403, reason)
