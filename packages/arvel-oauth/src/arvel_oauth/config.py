"""OAuth configuration via ``OAUTH_*`` environment variables.

Each provider is configured by setting its client credentials. A provider is
considered "configured" only when both its client id and secret are present
(Apple uses team/key/private-key instead of a secret).
"""

from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class OAuthConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    use_pkce: bool = Field(default=True, alias="OAUTH_USE_PKCE")
    error_redirect_url: str = Field(default="/login", alias="OAUTH_ERROR_REDIRECT_URL")
    success_redirect_url: str = Field(default="/", alias="OAUTH_SUCCESS_REDIRECT_URL")
    allow_http_issuer: bool = Field(default=False, alias="OAUTH_ALLOW_HTTP_ISSUER")

    google_client_id: str = Field(default="", alias="OAUTH_GOOGLE_CLIENT_ID")
    google_client_secret: SecretStr = Field(
        default=SecretStr(""), alias="OAUTH_GOOGLE_CLIENT_SECRET"
    )
    google_redirect_uri: str = Field(default="", alias="OAUTH_GOOGLE_REDIRECT_URI")

    github_client_id: str = Field(default="", alias="OAUTH_GITHUB_CLIENT_ID")
    github_client_secret: SecretStr = Field(
        default=SecretStr(""), alias="OAUTH_GITHUB_CLIENT_SECRET"
    )
    github_redirect_uri: str = Field(default="", alias="OAUTH_GITHUB_REDIRECT_URI")

    microsoft_client_id: str = Field(default="", alias="OAUTH_MICROSOFT_CLIENT_ID")
    microsoft_client_secret: SecretStr = Field(
        default=SecretStr(""), alias="OAUTH_MICROSOFT_CLIENT_SECRET"
    )
    microsoft_redirect_uri: str = Field(default="", alias="OAUTH_MICROSOFT_REDIRECT_URI")
    microsoft_tenant: str = Field(default="common", alias="OAUTH_MICROSOFT_TENANT")

    apple_client_id: str = Field(default="", alias="OAUTH_APPLE_CLIENT_ID")
    apple_team_id: str = Field(default="", alias="OAUTH_APPLE_TEAM_ID")
    apple_key_id: str = Field(default="", alias="OAUTH_APPLE_KEY_ID")
    apple_private_key: SecretStr = Field(default=SecretStr(""), alias="OAUTH_APPLE_PRIVATE_KEY")
    apple_redirect_uri: str = Field(default="", alias="OAUTH_APPLE_REDIRECT_URI")

    oidc_issuer_url: str = Field(default="", alias="OAUTH_OIDC_ISSUER_URL")
    oidc_client_id: str = Field(default="", alias="OAUTH_OIDC_CLIENT_ID")
    oidc_client_secret: SecretStr = Field(default=SecretStr(""), alias="OAUTH_OIDC_CLIENT_SECRET")
    oidc_redirect_uri: str = Field(default="", alias="OAUTH_OIDC_REDIRECT_URI")


__all__ = ["OAuthConfig"]
