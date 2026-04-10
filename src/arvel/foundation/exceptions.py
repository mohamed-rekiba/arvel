"""Foundation exception hierarchy.

All exceptions are typed and carry context about what failed and why.
Production error responses strip internal details unless APP_DEBUG=true.
"""

from __future__ import annotations


class ArvelError(Exception):
    """Base for all framework exceptions."""


class ConfigurationError(ArvelError):
    """Raised when config validation fails at startup.

    Attributes:
        field: The config field that failed validation (if applicable).
        env_var: The environment variable name that's missing or invalid.
    """

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        env_var: str | None = None,
    ) -> None:
        super().__init__(message)
        self.field = field
        self.env_var = env_var


class ProviderNotFoundError(ArvelError):
    """Raised when a module's provider.py exists but has no ServiceProvider subclass.

    Attributes:
        module_path: Filesystem path to the module that was scanned.
    """

    def __init__(self, message: str, *, module_path: str) -> None:
        super().__init__(message)
        self.module_path = module_path


class BootError(ArvelError):
    """Raised when a provider's boot() method fails.

    Attributes:
        provider_name: The class name of the provider that failed.
        cause: The original exception.
    """

    def __init__(
        self,
        message: str,
        *,
        provider_name: str,
        cause: Exception,
    ) -> None:
        super().__init__(message)
        self.provider_name = provider_name
        self.cause = cause


class DependencyError(ArvelError):
    """Raised when a requested binding cannot be resolved.

    Attributes:
        requested_type: The type that was requested but has no binding.
    """

    def __init__(self, message: str, *, requested_type: type) -> None:
        super().__init__(message)
        self.requested_type = requested_type
