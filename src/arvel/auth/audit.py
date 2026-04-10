"""Auth audit logger — structured events using JWT claims (sub as anchor).

Logs authentication and authorization events in a structured format
suitable for security monitoring, compliance, and incident response.
Never logs secrets, tokens, or PII beyond what's in the claims.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from arvel.logging import Log
from arvel.support.utils import data_get

logger = Log.named("arvel.auth.audit")


class AuditEvent(StrEnum):
    """Standard audit event types."""

    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    LOGOUT = "logout"
    TOKEN_REFRESH = "token_refresh"  # noqa: S105
    TOKEN_REVOKED = "token_revoked"  # noqa: S105
    REGISTER = "register"
    PASSWORD_RESET_REQUEST = "password_reset_request"  # noqa: S105
    PASSWORD_RESET_COMPLETE = "password_reset_complete"  # noqa: S105
    EMAIL_VERIFIED = "email_verified"
    AUTHZ_ALLOWED = "authz_allowed"
    AUTHZ_DENIED = "authz_denied"
    OAUTH_CALLBACK = "oauth_callback"
    OAUTH_LINK = "oauth_link"


class AuditLogger:
    """Structured audit logger that uses ``sub`` from JWT claims as the actor.

    All events are logged via the standard ``logging`` module using
    structured extra fields. Integrates with structlog if configured.
    """

    def __init__(self, *, enabled: bool = True, include_roles: bool = True) -> None:
        self._enabled = enabled
        self._include_roles = include_roles

    def _extract_identity(self, claims: dict[str, Any] | None) -> tuple[str, list[str], list[str]]:
        """Extract sub, roles, groups from claims."""
        if not claims:
            return "", [], []

        sub: str = data_get(claims, "sub", "")
        roles: list[str] = []
        groups: list[str] = []

        if self._include_roles:
            roles = data_get(claims, "realm_access.roles", [])
            if not roles:
                roles = data_get(claims, "roles", [])
            groups = data_get(claims, "groups", [])

        return sub, roles, groups

    def log(
        self,
        event: AuditEvent | str,
        *,
        claims: dict[str, Any] | None = None,
        action: str = "",
        resource: str = "",
        result: str = "",
        ip: str = "",
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Log a structured audit event. Returns the event dict."""
        if not self._enabled:
            return {}

        event_name = event.value if isinstance(event, AuditEvent) else event
        sub, roles, groups = self._extract_identity(claims)

        record: dict[str, Any] = {
            "event": event_name,
            "sub": sub,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        optional: dict[str, Any] = {
            "action": action,
            "resource": resource,
            "result": result,
            "ip": ip,
        }
        for key, val in optional.items():
            if val:
                record[key] = val
        if roles:
            record["roles"] = roles
        if groups:
            record["groups"] = groups
        if extra:
            record["extra"] = extra

        logger.info(
            "audit: %s sub=%s action=%s resource=%s result=%s",
            event_name,
            sub,
            action,
            resource,
            result,
            extra={"audit": record},
        )

        return record

    def log_authz(
        self,
        *,
        claims: dict[str, Any],
        action: str,
        resource: str,
        allowed: bool,
        ip: str = "",
    ) -> dict[str, Any]:
        """Log an authorization decision."""
        event = AuditEvent.AUTHZ_ALLOWED if allowed else AuditEvent.AUTHZ_DENIED
        return self.log(
            event,
            claims=claims,
            action=action,
            resource=resource,
            result="allowed" if allowed else "denied",
            ip=ip,
        )

    def log_auth(
        self,
        event: AuditEvent,
        *,
        claims: dict[str, Any] | None = None,
        ip: str = "",
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Log an authentication event (login, logout, register, etc.)."""
        return self.log(event, claims=claims, ip=ip, extra=extra)
