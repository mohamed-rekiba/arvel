"""Tests for auth audit logger."""

from __future__ import annotations

import logging

from arvel.auth.audit import AuditEvent, AuditLogger


class TestAuditLogger:
    def test_log_auth_event(self) -> None:
        audit = AuditLogger()
        claims = {"sub": "user-123", "realm_access": {"roles": ["admin"]}}

        record = audit.log_auth(AuditEvent.LOGIN_SUCCESS, claims=claims, ip="10.0.0.1")

        assert record["event"] == "login_success"
        assert record["sub"] == "user-123"
        assert record["ip"] == "10.0.0.1"
        assert record["roles"] == ["admin"]
        assert "timestamp" in record

    def test_log_authz_allowed(self) -> None:
        audit = AuditLogger()
        claims = {"sub": "user-456", "groups": ["/editors"]}

        record = audit.log_authz(
            claims=claims,
            action="update",
            resource="Post:789",
            allowed=True,
        )

        assert record["event"] == "authz_allowed"
        assert record["sub"] == "user-456"
        assert record["action"] == "update"
        assert record["resource"] == "Post:789"
        assert record["result"] == "allowed"
        assert record["groups"] == ["/editors"]

    def test_log_authz_denied(self) -> None:
        audit = AuditLogger()
        claims = {"sub": "user-000"}

        record = audit.log_authz(
            claims=claims,
            action="delete",
            resource="User:1",
            allowed=False,
        )

        assert record["event"] == "authz_denied"
        assert record["result"] == "denied"

    def test_disabled_returns_empty(self) -> None:
        audit = AuditLogger(enabled=False)
        claims = {"sub": "user-123"}

        record = audit.log_auth(AuditEvent.LOGIN_SUCCESS, claims=claims)
        assert record == {}

    def test_no_claims_sets_empty_sub(self) -> None:
        audit = AuditLogger()
        record = audit.log(AuditEvent.LOGOUT)

        assert record["sub"] == ""
        assert record["event"] == "logout"

    def test_exclude_roles_when_disabled(self) -> None:
        audit = AuditLogger(include_roles=False)
        claims = {"sub": "user-123", "realm_access": {"roles": ["admin"]}}

        record = audit.log_auth(AuditEvent.LOGIN_SUCCESS, claims=claims)

        assert "roles" not in record

    def test_extra_fields_included(self) -> None:
        audit = AuditLogger()
        record = audit.log(
            AuditEvent.OAUTH_CALLBACK,
            claims={"sub": "user-123"},
            extra={"provider": "keycloak"},
        )
        assert record["extra"] == {"provider": "keycloak"}

    def test_custom_event_string(self) -> None:
        audit = AuditLogger()
        record = audit.log("custom_event", claims={"sub": "user-123"})
        assert record["event"] == "custom_event"

    def test_log_writes_to_logger(self) -> None:
        import structlog

        structlog.configure(
            processors=[
                structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=False,
        )

        audit = AuditLogger()
        logger = logging.getLogger("arvel.auth.audit")
        logger.setLevel(logging.DEBUG)
        with _CaptureLogs(logger) as logs:
            audit.log_auth(
                AuditEvent.LOGIN_SUCCESS,
                claims={"sub": "user-log"},
                ip="1.2.3.4",
            )
        assert len(logs) >= 1
        assert "login_success" in logs[0].getMessage()


class _LogCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class _CaptureLogs:
    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger
        self._handler = _LogCapture()

    def __enter__(self) -> list[logging.LogRecord]:
        self._logger.addHandler(self._handler)
        return self._handler.records

    def __exit__(self, *args: object) -> None:
        self._logger.removeHandler(self._handler)
