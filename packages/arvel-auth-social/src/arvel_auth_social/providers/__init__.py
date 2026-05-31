"""Built-in social-auth providers."""

from __future__ import annotations

from arvel_auth_social.providers.apple import AppleProvider
from arvel_auth_social.providers.base import OAuthProvider
from arvel_auth_social.providers.github import GitHubProvider
from arvel_auth_social.providers.google import GoogleProvider
from arvel_auth_social.providers.microsoft import MicrosoftProvider
from arvel_auth_social.providers.oidc import OIDCProvider

__all__ = [
    "AppleProvider",
    "GitHubProvider",
    "GoogleProvider",
    "MicrosoftProvider",
    "OAuthProvider",
    "OIDCProvider",
]
