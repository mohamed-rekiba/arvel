"""OAuth route registration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import Response

if TYPE_CHECKING:
    from arvel_oauth.http.controller import OAuthController


def register_oauth_routes(
    router: APIRouter,
    *,
    controller: OAuthController,
    prefix: str = "/auth",
) -> None:
    """Mount ``{prefix}/{provider}/redirect`` and ``{prefix}/{provider}/callback``."""
    p = prefix.rstrip("/")

    async def handle_redirect(provider: str) -> Response:
        return await controller.redirect(provider)

    async def handle_callback(provider: str, request: Request) -> Response:
        return await controller.callback(provider, request)

    router.add_api_route(f"{p}/{{provider}}/redirect", handle_redirect, methods=["GET"])
    router.add_api_route(f"{p}/{{provider}}/callback", handle_callback, methods=["GET"])


__all__ = ["register_oauth_routes"]
