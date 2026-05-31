"""Built-in oauth providers."""

from __future__ import annotations

from arvel_oauth.providers.apple import AppleProvider
from arvel_oauth.providers.base import OAuthProvider
from arvel_oauth.providers.github import GitHubProvider
from arvel_oauth.providers.google import GoogleProvider
from arvel_oauth.providers.microsoft import MicrosoftProvider
from arvel_oauth.providers.oidc import OIDCProvider

__all__ = [
    "AppleProvider",
    "GitHubProvider",
    "GoogleProvider",
    "MicrosoftProvider",
    "OAuthProvider",
    "OIDCProvider",
]
