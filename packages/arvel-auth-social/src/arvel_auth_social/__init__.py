"""arvel-auth-social — OAuth2/OIDC social login for Arvel."""

from __future__ import annotations

from arvel_auth_social.config import SocialAuthConfig
from arvel_auth_social.dtos import OAuthToken, OAuthUser
from arvel_auth_social.exceptions import (
    DuplicateSocialAccount,
    InvalidOAuthState,
    OAuthExchangeError,
    OIDCDiscoveryError,
    SocialAuthError,
    SocialProviderNotFound,
)
from arvel_auth_social.linker import SocialAccountLinker
from arvel_auth_social.manager import SocialAuthManager
from arvel_auth_social.models import SocialAccount
from arvel_auth_social.provider import SocialAuthServiceProvider
from arvel_auth_social.providers import (
    AppleProvider,
    GitHubProvider,
    GoogleProvider,
    MicrosoftProvider,
    OAuthProvider,
    OIDCProvider,
)

__all__ = [
    "AppleProvider",
    "DuplicateSocialAccount",
    "GitHubProvider",
    "GoogleProvider",
    "InvalidOAuthState",
    "MicrosoftProvider",
    "OAuthExchangeError",
    "OAuthProvider",
    "OAuthToken",
    "OAuthUser",
    "OIDCDiscoveryError",
    "OIDCProvider",
    "SocialAccount",
    "SocialAccountLinker",
    "SocialAuthConfig",
    "SocialAuthError",
    "SocialAuthManager",
    "SocialAuthServiceProvider",
    "SocialProviderNotFound",
]
