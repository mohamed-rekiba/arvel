"""AuditValues column type — plain JSON passthrough and encrypted round-trip."""

from __future__ import annotations

from typing import Any

from arvel.facades.crypt import Crypt
from arvel_audit.types import AuditValues
from sqlalchemy.dialects.sqlite import dialect


def test_plain_values_pass_through_unencrypted() -> None:
    col = AuditValues(encrypt=False)
    payload: dict[str, Any] = {"name": "bolt", "price": 7}
    assert col.process_bind_param(payload, dialect()) == payload
    assert col.process_result_value(payload, dialect()) == payload


def test_encrypted_values_are_ciphertext_at_rest() -> None:
    col = AuditValues(encrypt=True)
    bound = col.process_bind_param({"card_number": "4111111111111111"}, dialect())

    assert isinstance(bound, str)
    assert "4111111111111111" not in bound
    assert Crypt.decrypt_string(bound) == '{"card_number": "4111111111111111"}'
    assert col.process_result_value(bound, dialect()) == {"card_number": "4111111111111111"}


def test_none_passes_through() -> None:
    col = AuditValues(encrypt=True)
    assert col.process_bind_param(None, dialect()) is None
    assert col.process_result_value(None, dialect()) is None
