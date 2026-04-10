"""Tests for AuthGuardMiddleware with ClaimsMapper integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from arvel.auth.auth_manager import AuthManager
from arvel.auth.claims import ClaimsMapper, ClaimsMapperConfig
from arvel.auth.guard import AuthGuardMiddleware
from arvel.auth.guards.jwt_guard import JwtGuard
from arvel.auth.tokens import TokenService

if TYPE_CHECKING:
    from starlette.requests import Request

SECRET = "test-secret-key-for-guard-claims"


def _create_token_service() -> TokenService:
    return TokenService(SECRET, issuer="test", audience="test-app")


async def _echo(request: Request) -> JSONResponse:
    state = request.scope.get("state", {})
    return JSONResponse(
        {
            "user_id": state.get("auth_user_id"),
            "roles": state.get("auth_roles", []),
            "groups": state.get("auth_groups", []),
        }
    )


def _create_app(
    claims_mapper: ClaimsMapper | None = None,
) -> Starlette:
    ts = _create_token_service()
    mapper_fn = None
    if claims_mapper is not None:

        def _mapper_fn(claims: dict[str, object]) -> dict[str, object]:
            extracted = claims_mapper.extract(claims)
            return {
                "sub": extracted.sub,
                "roles": extracted.roles,
                "groups": extracted.groups,
                **claims,
            }

        mapper_fn = _mapper_fn
    auth_manager = AuthManager(
        guards={"jwt": JwtGuard(token_service=ts, claims_mapper=mapper_fn)},
        default="jwt",
    )
    app = Starlette(routes=[Route("/protected", _echo, methods=["GET"])])
    app.add_middleware(
        AuthGuardMiddleware,
        auth_manager=auth_manager,
        exclude_paths={"/public"},
    )
    return app


class TestGuardWithClaims:
    def test_no_claims_mapper_skips_role_extraction(self) -> None:
        ts = _create_token_service()
        token = ts.create_access_token("user-1")
        client = TestClient(_create_app(claims_mapper=None))

        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["user_id"] == "user-1"
        assert body["roles"] == []
        assert body["groups"] == []

    def test_claims_mapper_extracts_roles_and_groups(self) -> None:
        ts = _create_token_service()
        extra_claims = {
            "realm_access": {"roles": ["admin", "editor"]},
            "groups": ["/org/team-a"],
        }
        token = ts.create_access_token("user-2", extra_claims=extra_claims)

        mapper = ClaimsMapper(
            ClaimsMapperConfig(
                role_claim_paths=["realm_access.roles"],
                group_claim_paths=["groups"],
            )
        )
        client = TestClient(_create_app(claims_mapper=mapper))

        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["user_id"] == "user-2"
        assert body["roles"] == ["admin", "editor"]
        assert body["groups"] == ["/org/team-a"]

    def test_claims_with_no_roles_returns_empty(self) -> None:
        ts = _create_token_service()
        token = ts.create_access_token("user-3")

        mapper = ClaimsMapper()
        client = TestClient(_create_app(claims_mapper=mapper))

        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["roles"] == []
        assert body["groups"] == []
