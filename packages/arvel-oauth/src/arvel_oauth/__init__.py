"""arvel-oauth — OAuth2/OIDC login for Arvel."""

from __future__ import annotations

from arvel_oauth.config import OAuthConfig
from arvel_oauth.dtos import OAuthToken, OAuthUser
from arvel_oauth.exceptions import (
    DuplicateOAuthAccount,
    InvalidOAuthState,
    OAuthError,
    OAuthExchangeError,
    OIDCDiscoveryError,
    ProviderNotFound,
)
from arvel_oauth.linker import OAuthAccountLinker
from arvel_oauth.manager import OAuthManager
from arvel_oauth.models import OAuthAccount
from arvel_oauth.provider import OAuthServiceProvider
from arvel_oauth.providers import (
    AppleProvider,
    GitHubProvider,
    GoogleProvider,
    MicrosoftProvider,
    OAuthProvider,
    OIDCProvider,
)

__all__ = [
    "AppleProvider",
    "DuplicateOAuthAccount",
    "GitHubProvider",
    "GoogleProvider",
    "InvalidOAuthState",
    "MicrosoftProvider",
    "OAuthAccount",
    "OAuthAccountLinker",
    "OAuthConfig",
    "OAuthError",
    "OAuthExchangeError",
    "OAuthManager",
    "OAuthProvider",
    "OAuthServiceProvider",
    "OAuthToken",
    "OAuthUser",
    "OIDCDiscoveryError",
    "OIDCProvider",
    "ProviderNotFound",
]
