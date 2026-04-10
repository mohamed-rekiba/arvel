"""Claims mapper — extract roles and groups from JWT/OIDC claims.

Supports configurable claim paths for different OIDC providers:
- Keycloak: ``realm_access.roles``, ``groups``
- Azure AD: ``roles``, ``groups``
- Auth0: ``https://myapp/roles``
- Generic: any dot-separated path into the claims dict
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from arvel.support.utils import data_get


@dataclass
class ClaimsMapperConfig:
    """Configuration for extracting roles and groups from claims.

    Each path is a dot-separated key into the claims dict.
    Multiple paths can be specified — all are merged.
    """

    role_claim_paths: list[str] = field(default_factory=lambda: ["realm_access.roles", "roles"])
    group_claim_paths: list[str] = field(default_factory=lambda: ["groups"])


@dataclass
class ExtractedClaims:
    """Roles and groups extracted from a JWT/OIDC claims payload."""

    sub: str
    roles: list[str] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


def _deduplicate(items: list[str]) -> list[str]:
    """Remove duplicates while preserving order."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


class ClaimsMapper:
    """Extracts roles and groups from JWT/OIDC claims using configurable paths."""

    def __init__(self, config: ClaimsMapperConfig | None = None) -> None:
        self._config = config or ClaimsMapperConfig()

    def extract(self, claims: dict[str, Any]) -> ExtractedClaims:
        """Extract sub, roles, and groups from a claims payload."""
        sub = str(claims.get("sub", ""))
        roles = self._collect(claims, self._config.role_claim_paths)
        groups = self._collect(claims, self._config.group_claim_paths)

        return ExtractedClaims(
            sub=sub,
            roles=_deduplicate(roles),
            groups=_deduplicate(groups),
            raw=claims,
        )

    def _collect(self, claims: dict[str, Any], paths: list[str]) -> list[str]:
        """Collect string values from multiple claim paths."""
        result: list[str] = []
        for path in paths:
            value = data_get(claims, path)
            if isinstance(value, list):
                result.extend(str(v) for v in value)
            elif isinstance(value, str):
                result.append(value)
        return result
