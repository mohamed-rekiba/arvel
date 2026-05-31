"""HTTP flow for OAuth authentication."""

from __future__ import annotations

from arvel_oauth.http.controller import OAuthController
from arvel_oauth.http.routes import register_oauth_routes

__all__ = ["OAuthController", "register_oauth_routes"]
