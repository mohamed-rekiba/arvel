"""OAuth2/OIDC provider contracts and built-in provider configurations.

Defines the ``OAuthProviderContract`` ABC and concrete configs for
Google, GitHub, Microsoft, and Apple. Also includes a generic OIDC
provider that auto-discovers endpoints via ``.well-known/openid-configuration``.
"""

from __future__ import annotations

import hashlib
import os
from abc import ABC, abstractmethod
from base64 import urlsafe_b64encode
from dataclasses import dataclass, field
from typing import Any


@dataclass
class OAuthToken:
    """Token payload returned from an OAuth2 token exchange."""

    access_token: str
    token_type: str = "bearer"  # noqa: S105
    refresh_token: str | None = None
    expires_in: int | None = None
    id_token: str | None = None
    scope: str | None = None


@dataclass
class OAuthUser:
    """Normalized user profile from an OAuth2 provider."""

    provider: str
    provider_id: str
    email: str | None = None
    name: str | None = None
    avatar_url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class OAuthProviderContract(ABC):
    """Contract for OAuth2/OIDC providers.

    Each provider implements authorization URL generation, token exchange,
    and user profile fetching.
    """

    @abstractmethod
    def get_authorization_url(self, state: str, code_challenge: str | None = None) -> str:
        """Build the URL to redirect the user to for OAuth consent."""

    @abstractmethod
    async def exchange_code(self, code: str, code_verifier: str | None = None) -> OAuthToken:
        """Exchange an authorization code for tokens."""

    @abstractmethod
    async def get_user(self, token: OAuthToken) -> OAuthUser:
        """Fetch the authenticated user's profile from the provider."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'google', 'github')."""


@dataclass
class OAuthProviderConfig:
    """Configuration for an OAuth2/OIDC provider."""

    provider_name: str
    client_id: str
    client_secret: str
    authorize_url: str
    token_url: str
    userinfo_url: str
    scopes: list[str] = field(default_factory=lambda: ["openid", "email", "profile"])
    redirect_uri: str = ""
    use_pkce: bool = True


def generate_pkce_pair() -> tuple[str, str]:
    """Generate a PKCE code_verifier and code_challenge (S256)."""
    verifier = urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode("ascii")
    challenge = (
        urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    return verifier, challenge


def generate_oauth_state() -> str:
    """Generate a cryptographically random state parameter."""
    return os.urandom(32).hex()


BUILTIN_PROVIDERS: dict[str, dict[str, str]] = {
    "google": {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://www.googleapis.com/oauth2/v3/userinfo",
    },
    "github": {
        "authorize_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "userinfo_url": "https://api.github.com/user",
    },
    "microsoft": {
        "authorize_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "userinfo_url": "https://graph.microsoft.com/v1.0/me",
    },
    "apple": {
        "authorize_url": "https://appleid.apple.com/auth/authorize",
        "token_url": "https://appleid.apple.com/auth/token",
        "userinfo_url": "",
    },
}


@dataclass
class OIDCDiscoveryDocument:
    """Parsed OIDC discovery document from .well-known/openid-configuration."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: str
    jwks_uri: str
    scopes_supported: list[str] = field(default_factory=list)
    response_types_supported: list[str] = field(default_factory=list)
    claims_supported: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


def discover_oidc_config(
    issuer_url: str,
    *,
    client_id: str = "",
    client_secret: str = "",
) -> tuple[OIDCDiscoveryDocument, OAuthProviderConfig]:
    """Fetch OIDC discovery document and build an OAuthProviderConfig.

    Accepts an issuer URL (e.g., ``https://keycloak.example.com/realms/myrealm``)
    and fetches ``{issuer}/.well-known/openid-configuration``.

    Returns (discovery_doc, provider_config) tuple.
    """
    import urllib.request

    well_known_url = issuer_url.rstrip("/") + "/.well-known/openid-configuration"

    req = urllib.request.Request(well_known_url, headers={"Accept": "application/json"})  # noqa: S310
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
        import json

        data: dict[str, Any] = json.loads(resp.read())

    doc = OIDCDiscoveryDocument(
        issuer=data.get("issuer", issuer_url),
        authorization_endpoint=data["authorization_endpoint"],
        token_endpoint=data["token_endpoint"],
        userinfo_endpoint=data.get("userinfo_endpoint", ""),
        jwks_uri=data.get("jwks_uri", ""),
        scopes_supported=data.get("scopes_supported", []),
        response_types_supported=data.get("response_types_supported", []),
        claims_supported=data.get("claims_supported", []),
        raw=data,
    )

    provider_name = issuer_url.rstrip("/").rsplit("/", 1)[-1]

    config = OAuthProviderConfig(
        provider_name=provider_name,
        client_id=client_id,
        client_secret=client_secret,
        authorize_url=doc.authorization_endpoint,
        token_url=doc.token_endpoint,
        userinfo_url=doc.userinfo_endpoint,
    )

    return doc, config


class OAuthProviderRegistry:
    """Registry of configured OAuth2/OIDC providers."""

    def __init__(self) -> None:
        self._providers: dict[str, OAuthProviderContract] = {}

    def register(self, provider: OAuthProviderContract) -> None:
        self._providers[provider.name] = provider

    def get(self, name: str) -> OAuthProviderContract | None:
        return self._providers.get(name)

    def all(self) -> dict[str, OAuthProviderContract]:
        return dict(self._providers)

    @property
    def names(self) -> list[str]:
        return list(self._providers)
