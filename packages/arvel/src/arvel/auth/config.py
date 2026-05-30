"""Auth subsystem configuration models."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class GuardConfig(BaseModel):
    driver: str
    provider: str


class ProviderConfig(BaseModel):
    driver: str
    model: str
    """Dotted import path to the User model, e.g. ``app.models.user.User``."""
    resource: str | None = None
    """Optional dotted path to a custom UserResource Pydantic model.

    When set, ``AuthController`` uses this class to serialize users in
    ``register`` and ``me`` responses. Useful for apps that extend the
    base ``UserResource`` with extra fields (e.g. ``theme``, ``role``).

    Defaults to ``arvel.auth.http.resources.UserResource``.
    """


class HashConfig(BaseModel):
    driver: str = "bcrypt"
    rounds: int = 12


class JwtConfig(BaseModel):
    """JWT access-token settings."""

    secret: str = Field(default="", min_length=32)
    algorithm: str = "HS256"
    ttl_seconds: int = 900
    issuer: str = ""
    audience: str = ""


class RefreshConfig(BaseModel):
    """Opaque refresh-token + cookie settings."""

    ttl_seconds: int = 14 * 24 * 3600
    cookie_name: str = "__Host-refresh"
    cookie_secure: bool = True
    csrf_cookie_name: str = "_csrf"
    csrf_cookie_secure: bool = True
    csrf_header: str = "X-CSRF-TOKEN"


class RoutesConfig(BaseModel):
    """Auth route mounting settings."""

    enabled: bool = True
    prefix: str = "/api/auth"


class AuthConfig(BaseModel):
    default: str
    guards: dict[str, GuardConfig] = {}
    providers: dict[str, ProviderConfig] = {}
    hash: HashConfig = HashConfig()
    jwt: JwtConfig = JwtConfig()
    refresh: RefreshConfig = RefreshConfig()
    routes: RoutesConfig = RoutesConfig()
    broker_class: str | None = None
    """Dotted import path to a custom auth broker class.

    When set, this class is instantiated instead of the default
    :class:`~arvel.auth.broker.AuthBroker` and bound at ``"auth.broker"``
    in the container.
    """

    @field_validator("default")
    @classmethod
    def default_must_not_be_empty(cls, v: str) -> str:
        if not v:
            msg = "auth.default must not be empty"
            raise ValueError(msg)
        return v
