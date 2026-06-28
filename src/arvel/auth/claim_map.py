"""arvel.auth.claim_map — translate external IdP claim VALUES into arvel ``Role`` names (DR-0013).

There is no ``idp_group`` entity. An IdP's groups/roles are external strings; this pure translator
maps them to arvel ``Role`` names via an app-supplied mapping, **source-agnostic** across claim
paths (``groups``, ``realm_access.roles``, …). Unknown values grant nothing. The resulting role
names are unioned with a user's direct grants at resolution time and are never persisted as
membership (DR-0011). Grounded in DR-0011 / DR-0013 + the auth-rearchitecture architecture doc.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, cast


def _claim_values(claims: Mapping[str, Any], claim_paths: tuple[str, ...]) -> list[str]:
    """Collect the string values found at each configured (dotted) claim path."""
    from arvel.support.helpers import data_get

    values: list[str] = []
    for path in claim_paths:
        found = data_get(claims, path)
        if found is None:
            continue
        if isinstance(found, str):
            values.append(found)
        elif isinstance(found, (list, tuple, set)):
            values.extend(str(v) for v in cast("Iterable[Any]", found))
        else:
            values.append(str(found))
    return values


def roles_for_claims(
    claims: Mapping[str, Any],
    mapping: Mapping[str, Iterable[str] | str],
    *,
    claim_paths: Iterable[str] = ("groups",),
) -> set[str]:
    """Map external claim values to arvel role names.

    ``mapping`` keys are external claim values; values are one role name or several. Any claim
    value absent from ``mapping`` grants nothing (safe-by-default — no auto-map-by-name).
    """
    roles: set[str] = set()
    for value in _claim_values(claims, tuple(claim_paths)):
        mapped = mapping.get(value)
        if mapped is None:
            continue
        if isinstance(mapped, str):
            roles.add(mapped)
        else:
            roles.update(mapped)
    return roles
