"""Auth module — login, JWT tokens, guards, password reset, OAuth2/OIDC, claims, and audit."""

import arvel.auth.migration as _migration  # noqa: F401 — registers framework migrations
from arvel.auth.config import AuthSettings as AuthSettings

__all__ = ["AuthSettings"]
