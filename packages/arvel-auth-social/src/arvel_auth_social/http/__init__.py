"""HTTP flow for social authentication."""

from __future__ import annotations

from arvel_auth_social.http.controller import SocialAuthController
from arvel_auth_social.http.routes import register_social_routes

__all__ = ["SocialAuthController", "register_social_routes"]
