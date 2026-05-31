"""OAuth exception hierarchy."""

from __future__ import annotations


class OAuthError(Exception):
    """Base class for all oauth failures."""


class ProviderNotFound(OAuthError):
    """Raised when an unknown provider name is requested."""

    def __init__(self, name: str, available: list[str]) -> None:
        self.name = name
        self.available = available
        super().__init__(
            f"No OAuth provider named {name!r}. Configured providers: "
            f"{', '.join(available) or '(none)'}."
        )


class InvalidOAuthState(OAuthError):
    """Raised when the callback ``state`` does not match the stored value."""

    def __init__(self) -> None:
        super().__init__("OAuth state mismatch — possible CSRF or expired flow.")


class OAuthExchangeError(OAuthError):
    """Raised when the provider rejects the authorization-code exchange."""


class OIDCDiscoveryError(OAuthError):
    """Raised when an OIDC issuer's discovery document can't be fetched/parsed."""

    def __init__(self, issuer: str, detail: str) -> None:
        self.issuer = issuer
        super().__init__(f"OIDC discovery failed for {issuer!r}: {detail}")


class DuplicateOAuthAccount(OAuthError):
    """Raised when a (provider, provider_id) pair is already linked."""

    def __init__(self, provider: str, provider_id: str) -> None:
        self.provider = provider
        self.provider_id = provider_id
        super().__init__(f"OAuth account {provider}:{provider_id} is already linked.")


__all__ = [
    "DuplicateOAuthAccount",
    "InvalidOAuthState",
    "OAuthError",
    "OAuthExchangeError",
    "OIDCDiscoveryError",
    "ProviderNotFound",
]
