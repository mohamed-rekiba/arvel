"""Auth route registration.

``register_auth_routes`` wires all 9 auth endpoints onto a supplied
``APIRouter``. Call this from ``AuthServiceProvider.boot()`` so the
framework mounts the routes at application startup.

Usage::

    from fastapi import APIRouter
    from arvel.auth.http.controller import AuthController
    from arvel.auth.http.routes import register_auth_routes

    router = APIRouter()
    controller = AuthController(auth=..., passwords=..., email_verification=...)
    register_auth_routes(router, controller=controller)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, status
from starlette.requests import Request
from starlette.responses import Response

from arvel.auth.http.requests import (
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
)
from arvel.auth.http.resources import AuthEnvelope, LoginResponse, UserResource

if TYPE_CHECKING:
    from arvel.auth.http.controller import AuthController


def register_auth_routes(
    router: APIRouter,
    *,
    controller: AuthController,
    prefix: str = "/auth",
) -> None:
    """Mount all auth endpoints on ``router`` under ``prefix``.

    This is the hook the ``AuthServiceProvider`` calls in ``boot()``.
    Integration tests import it directly:

        from arvel.auth.http.routes import register_auth_routes
    """
    p = prefix.rstrip("/")

    async def handle_register(payload: RegisterRequest) -> Any:
        return await controller.register(payload)

    async def handle_login(payload: LoginRequest, response: Response) -> Any:
        return await controller.login(payload, response)

    async def handle_refresh(request: Request, response: Response) -> Any:
        return await controller.refresh(request, response)

    async def handle_logout(request: Request, response: Response) -> Response:
        return await controller.logout(request, response)

    async def handle_me(request: Request) -> Any:
        return await controller.me(request)

    async def handle_forgot_password(payload: ForgotPasswordRequest) -> Any:
        return await controller.forgot_password(payload)

    async def handle_reset_password(payload: ResetPasswordRequest) -> Any:
        return await controller.reset_password(payload)

    async def handle_verify_email(signed: str) -> Any:
        return await controller.verify_email(signed)

    async def handle_verify_email_resend(request: Request) -> Any:
        return await controller.verify_email_resend(request)

    router.add_api_route(
        f"{p}/register",
        handle_register,
        methods=["POST"],
        status_code=status.HTTP_201_CREATED,
        response_model=AuthEnvelope[UserResource],
    )
    router.add_api_route(
        f"{p}/login",
        handle_login,
        methods=["POST"],
        status_code=status.HTTP_200_OK,
        response_model=LoginResponse,
    )
    router.add_api_route(
        f"{p}/refresh",
        handle_refresh,
        methods=["POST"],
        status_code=status.HTTP_200_OK,
        response_model=LoginResponse,
    )
    router.add_api_route(
        f"{p}/logout",
        handle_logout,
        methods=["POST"],
        status_code=status.HTTP_204_NO_CONTENT,
    )
    router.add_api_route(
        f"{p}/me",
        handle_me,
        methods=["GET"],
        status_code=status.HTTP_200_OK,
        response_model=AuthEnvelope[UserResource],
    )
    router.add_api_route(
        f"{p}/forgot-password",
        handle_forgot_password,
        methods=["POST"],
        status_code=status.HTTP_202_ACCEPTED,
    )
    router.add_api_route(
        f"{p}/reset-password",
        handle_reset_password,
        methods=["POST"],
        status_code=status.HTTP_200_OK,
    )
    router.add_api_route(
        f"{p}/verify/{{signed}}",
        handle_verify_email,
        methods=["GET"],
        status_code=status.HTTP_200_OK,
    )
    router.add_api_route(
        f"{p}/verify/resend",
        handle_verify_email_resend,
        methods=["POST"],
        status_code=status.HTTP_200_OK,
    )


__all__ = ["register_auth_routes"]
