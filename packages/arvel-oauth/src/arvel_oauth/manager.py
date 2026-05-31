"""OAuthManager — resolves configured providers by name."""

from __future__ import annotations

from collections.abc import Callable

import httpx

from arvel_oauth.config import OAuthConfig
from arvel_oauth.exceptions import ProviderNotFound
from arvel_oauth.providers import (
    AppleProvider,
    GitHubProvider,
    GoogleProvider,
    MicrosoftProvider,
    OAuthProvider,
    OIDCProvider,
)


class OAuthManager:
    """Builds provider instances from a :class:`OAuthConfig`."""

    def __init__(
        self,
        config: OAuthConfig,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config = config
        self._http_client = http_client

    def configured_providers(self) -> list[str]:
        names: list[str] = []
        c = self._config
        if c.google_client_id and c.google_client_secret.get_secret_value():
            names.append("google")
        if c.github_client_id and c.github_client_secret.get_secret_value():
            names.append("github")
        if c.microsoft_client_id and c.microsoft_client_secret.get_secret_value():
            names.append("microsoft")
        if c.apple_client_id and c.apple_private_key.get_secret_value():
            names.append("apple")
        if c.oidc_issuer_url and c.oidc_client_id:
            names.append("oidc")
        return names

    def provider(self, name: str) -> OAuthProvider:
        """Return a configured provider. ``oidc`` is built via :meth:`oidc` (async)."""
        builders: dict[str, Callable[[], OAuthProvider]] = {
            "google": self._google,
            "github": self._github,
            "microsoft": self._microsoft,
            "apple": self._apple,
        }
        builder = builders.get(name)
        if builder is None:
            raise ProviderNotFound(name, self.configured_providers())
        return builder()

    async def oidc(self) -> OIDCProvider:
        """Build the generic OIDC provider via discovery."""
        c = self._config
        if not (c.oidc_issuer_url and c.oidc_client_id):
            raise ProviderNotFound("oidc", self.configured_providers())
        return await OIDCProvider.discover(
            issuer=c.oidc_issuer_url,
            client_id=c.oidc_client_id,
            client_secret=c.oidc_client_secret.get_secret_value(),
            redirect_uri=c.oidc_redirect_uri,
            use_pkce=c.use_pkce,
            allow_http=c.allow_http_issuer,
            http_client=self._http_client,
        )

    def _google(self) -> GoogleProvider:
        c = self._config
        return GoogleProvider(
            client_id=c.google_client_id,
            client_secret=c.google_client_secret.get_secret_value(),
            redirect_uri=c.google_redirect_uri,
            use_pkce=c.use_pkce,
            http_client=self._http_client,
        )

    def _github(self) -> GitHubProvider:
        c = self._config
        return GitHubProvider(
            client_id=c.github_client_id,
            client_secret=c.github_client_secret.get_secret_value(),
            redirect_uri=c.github_redirect_uri,
            http_client=self._http_client,
        )

    def _microsoft(self) -> MicrosoftProvider:
        c = self._config
        return MicrosoftProvider(
            client_id=c.microsoft_client_id,
            client_secret=c.microsoft_client_secret.get_secret_value(),
            redirect_uri=c.microsoft_redirect_uri,
            tenant=c.microsoft_tenant,
            use_pkce=c.use_pkce,
            http_client=self._http_client,
        )

    def _apple(self) -> AppleProvider:
        c = self._config
        return AppleProvider(
            client_id=c.apple_client_id,
            team_id=c.apple_team_id,
            key_id=c.apple_key_id,
            private_key=c.apple_private_key.get_secret_value(),
            redirect_uri=c.apple_redirect_uri,
            use_pkce=c.use_pkce,
            http_client=self._http_client,
        )


__all__ = ["OAuthManager"]
