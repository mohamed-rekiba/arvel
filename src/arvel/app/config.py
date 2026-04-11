"""Application root configuration."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from arvel.foundation.config import ModuleSettings


def _default_version() -> str:
    """Resolve the installed arvel version at import time."""
    try:
        from importlib.metadata import version

        return version("arvel")
    except Exception:
        return "0.0.0"


class AppSettings(BaseSettings):
    """Root application settings loaded from APP_* environment variables.

    FastAPI metadata fields (description, version, summary, etc.) are forwarded
    to the ``FastAPI()`` constructor at boot time.  Set them via environment
    variables (``APP_DESCRIPTION``, ``APP_VERSION``, …) or in ``config/app.py``.
    """

    app_name: str = "Arvel"
    app_env: str = "development"
    app_debug: bool = False
    app_key: SecretStr = SecretStr("")
    base_path: Path = Path()

    # -- FastAPI metadata (forwarded to the FastAPI constructor) ---------------
    app_description: str = ""
    app_version: str = _default_version()
    app_summary: str = ""
    app_terms_of_service: str = ""
    app_contact: dict[str, str] | None = None
    app_license_info: dict[str, str] | None = None
    app_openapi_tags: list[dict[str, Any]] | None = None

    # -- OpenAPI security schemes (injected into the generated OpenAPI spec) ---
    app_openapi_security_schemes: dict[str, dict[str, Any]] | None = None
    app_openapi_global_security: list[dict[str, list[str]]] | None = None

    # -- OpenAPI / docs URLs ---------------------------------------------------
    app_docs_url: str | None = "/docs"
    app_redoc_url: str | None = "/redoc"
    app_openapi_url: str = "/openapi.json"

    model_config = SettingsConfigDict(extra="ignore")

    # Populated by load_config(); not a pydantic field (underscore prefix).
    _module_settings: dict[type[ModuleSettings], ModuleSettings] = {}

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        object.__setattr__(self, "_module_settings", {})


settings_class = AppSettings
