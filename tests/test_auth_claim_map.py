"""Phase 3 — claim->Role translation (DR-0013) + ephemeral IdP-role union in HasRoles (DR-0011).

The translator is a pure function; the has_role union is tested without a DB by overriding roles().
"""

from __future__ import annotations

from typing import Any

import pytest

from arvel.auth.claim_map import roles_for_claims
from arvel.auth.permissions import HasRoles

# --- claim_map.roles_for_claims (DR-0013) -------------------------------------


def test_maps_group_values_to_roles() -> None:
    claims = {"groups": ["/eng/backend", "/ops"]}
    mapping = {"/eng/backend": "developer", "/ops": "operator"}
    assert roles_for_claims(claims, mapping) == {"developer", "operator"}


def test_unknown_values_grant_nothing() -> None:
    claims = {"groups": ["/eng/backend", "/random-unmapped"]}
    mapping = {"/eng/backend": "developer"}
    assert roles_for_claims(claims, mapping) == {"developer"}


def test_source_agnostic_claim_path() -> None:
    # Keycloak realm roles live under realm_access.roles, not `groups`.
    claims = {"realm_access": {"roles": ["admins", "viewers"]}}
    mapping = {"admins": "admin", "viewers": "viewer"}
    roles = roles_for_claims(claims, mapping, claim_paths=("realm_access.roles",))
    assert roles == {"admin", "viewer"}


def test_one_value_can_map_to_multiple_roles() -> None:
    claims = {"groups": ["staff"]}
    mapping = {"staff": ["employee", "badge-holder"]}
    assert roles_for_claims(claims, mapping) == {"employee", "badge-holder"}


def test_string_valued_claim() -> None:
    assert roles_for_claims({"groups": "admins"}, {"admins": "admin"}) == {"admin"}


def test_missing_claim_yields_empty() -> None:
    assert roles_for_claims({}, {"x": "y"}) == set()


# --- HasRoles ephemeral IdP-role union (DR-0011) ------------------------------


class _U(HasRoles):
    """A user with no persisted roles — isolates the ephemeral-union behaviour (no DB)."""

    async def roles(self, team: Any = None) -> list[Any]:
        return []


@pytest.mark.asyncio
async def test_has_role_includes_idp_roles() -> None:
    user = _U()
    user.set_idp_roles({"admin", "developer"})
    assert await user.has_role("admin") is True
    assert await user.has_role("developer") is True
    assert await user.has_role("nonexistent") is False


@pytest.mark.asyncio
async def test_idp_roles_replaced_not_accumulated() -> None:
    user = _U()
    user.set_idp_roles({"admin"})
    user.set_idp_roles({"viewer"})  # re-resolved at next login — replaces, not accumulates
    assert await user.has_role("admin") is False
    assert await user.has_role("viewer") is True


def test_carried_idp_roles_empty_by_default() -> None:
    assert _U()._carried_idp_roles() == set()
