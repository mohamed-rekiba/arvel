"""Security configuration — hashing, encryption, JWT, and auth settings."""

from __future__ import annotations

from typing import ClassVar

from arvel.foundation.config import ModuleSettings


class SecuritySettings(ModuleSettings):
    """Security module config. Env prefix: SECURITY_."""

    hash_driver: str = "bcrypt"
    bcrypt_rounds: int = 12
    argon2_time_cost: int = 3
    argon2_memory_cost: int = 65536
    argon2_parallelism: int = 4

    jwt_algorithm: str = "HS256"
    jwt_access_ttl_minutes: int = 60
    jwt_refresh_ttl_days: int = 30
    jwt_issuer: str = "arvel"
    jwt_audience: str = "arvel-app"

    csrf_enabled: bool = True
    csrf_exclude_prefixes: list[str] = ["/api/"]  # noqa: RUF012

    rate_limit_default: str = "60/minute"
    rate_limit_auth: str = "5/minute"

    reset_token_ttl_minutes: int = 60
    verify_token_ttl_hours: int = 24

    oidc_issuer_url: str = ""
    oidc_client_id: str = ""

    claims_role_paths: list[str] = ["realm_access.roles", "roles"]  # noqa: RUF012
    claims_group_paths: list[str] = ["groups"]  # noqa: RUF012

    audit_enabled: bool = True
    audit_include_roles: bool = True

    model_config: ClassVar[dict[str, str]] = {"env_prefix": "SECURITY_", "extra": "ignore"}


settings_class = SecuritySettings
