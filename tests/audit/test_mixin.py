"""Tests for Auditable mixin — redact field declaration."""

from __future__ import annotations

from typing import ClassVar

from arvel.audit.mixin import Auditable


class TestAuditableMixin:
    def test_default_redact_is_empty(self) -> None:
        class MyModel(Auditable):
            pass

        assert MyModel.__audit_redact__ == set()

    def test_custom_redact_fields(self) -> None:
        class SecureModel(Auditable):
            __audit_redact__: ClassVar[set[str]] = {"password", "ssn"}

        assert "password" in SecureModel.__audit_redact__
        assert "ssn" in SecureModel.__audit_redact__

    def test_subclass_inherits_redact_fields(self) -> None:
        class Parent(Auditable):
            __audit_redact__: ClassVar[set[str]] = {"secret"}

        class Child(Parent):
            pass

        assert "secret" in Child.__audit_redact__

    def test_subclass_overrides_redact_fields(self) -> None:
        class Parent(Auditable):
            __audit_redact__: ClassVar[set[str]] = {"old_field"}

        class Child(Parent):
            __audit_redact__: ClassVar[set[str]] = {"new_field"}

        assert Child.__audit_redact__ == {"new_field"}
