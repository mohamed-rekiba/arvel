"""Observability configuration via environment variables."""

from __future__ import annotations

import os
from typing import Annotated

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from arvel.config.exceptions import ConfigurationError


def _default_service_name() -> str:
    # OTEL_SERVICE_NAME takes priority; fall back to APP_NAME then "arvel"
    return os.environ.get("OTEL_SERVICE_NAME") or os.environ.get("APP_NAME") or "arvel"


class ObservabilityConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    sdk_disabled: bool = Field(default=False, alias="OTEL_SDK_DISABLED")
    otlp_endpoint: str = Field(default="", alias="OTEL_EXPORTER_OTLP_ENDPOINT")
    # Marked secret so it won't appear in repr/logs
    otlp_headers: SecretStr = Field(default=SecretStr(""), alias="OTEL_EXPORTER_OTLP_HEADERS")
    service_name: str = Field(default_factory=_default_service_name, alias="OTEL_SERVICE_NAME")

    log_level: str = Field(default="info", alias="LOG_LEVEL")
    log_format: str = Field(default="json", alias="LOG_FORMAT")
    log_redact_fields: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "password",
            "token",
            "secret",
            "authorization",
            "api_key",
            "private_key",
        ],
        alias="LOG_REDACT_FIELDS",
    )
    log_uvicorn_access: bool = Field(default=True, alias="LOG_UVICORN_ACCESS")

    metrics_enabled: bool = Field(default=False, alias="OBSERVABILITY_METRICS_ENABLED")
    metrics_allowed_cidrs: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["127.0.0.1/32"],
        alias="OBSERVABILITY_METRICS_ALLOWED_CIDRS",
    )

    request_middleware_enabled: bool = Field(
        default=True, alias="OBSERVABILITY_REQUEST_MIDDLEWARE_ENABLED"
    )

    # Empty list = no restriction (LBs/k8s probes reach /_health from arbitrary IPs).
    health_allowed_cidrs: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        alias="HEALTH_ALLOWED_CIDRS",
    )

    db_slow_query_ms: int = Field(default=200, alias="DB_SLOW_QUERY_MS")
    db_query_log_enabled: bool = Field(default=True, alias="DB_QUERY_LOG_ENABLED")

    @field_validator(
        "log_redact_fields",
        "metrics_allowed_cidrs",
        "health_allowed_cidrs",
        mode="before",
    )
    @classmethod
    def _split_csv(cls, v: object) -> object:
        # Env vars arrive as strings; accept "a,b,c" instead of forcing JSON arrays.
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @field_validator("log_level", mode="before")
    @classmethod
    def _validate_log_level(cls, v: object) -> object:
        valid = {"debug", "info", "warning", "warn", "error", "critical"}
        if isinstance(v, str) and v.lower() not in valid:
            raise ConfigurationError(
                f"Invalid log level {v!r}. Choose from: {', '.join(sorted(valid))}"
            )
        return v

    @model_validator(mode="after")
    def _resolve_service_name(self) -> ObservabilityConfig:
        # If OTEL_SERVICE_NAME wasn't set, pull from APP_NAME
        if not self.service_name:
            self.service_name = os.environ.get("APP_NAME") or "arvel"
        return self


__all__ = ["ObservabilityConfig"]
