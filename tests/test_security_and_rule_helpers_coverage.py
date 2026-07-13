"""Pure helper coverage: ``security._decode_key`` (bytes / urlsafe-fallback / invalid) and the
``validation.rules`` numeric guards (``_is_number``/``_check_ip``/``_check_decimal``/
``_check_multiple_of``)."""

from __future__ import annotations

import base64

import pytest

from arvel.security import _decode_key  # pyright: ignore[reportPrivateUsage]
from arvel.validation.rules import (
    _check_decimal,  # pyright: ignore[reportPrivateUsage]
    _check_ip,  # pyright: ignore[reportPrivateUsage]
    _check_multiple_of,  # pyright: ignore[reportPrivateUsage]
    _is_number,  # pyright: ignore[reportPrivateUsage]
)


def test_decode_key_accepts_raw_bytes() -> None:
    assert _decode_key(b"\x01" * 32) == b"\x01" * 32


def test_decode_key_falls_back_to_urlsafe_alphabet() -> None:
    raw = b"\xff" * 32  # urlsafe-encodes with '_' chars that standard b64 (validate) rejects
    key = base64.urlsafe_b64encode(raw).decode()
    assert "_" in key  # the branch we're exercising
    assert _decode_key(key) == raw


def test_decode_key_rejects_undecodable() -> None:
    with pytest.raises(ValueError, match="invalid encryption key encoding"):
        _decode_key("###not-base64###")


def test_rule_numeric_helpers() -> None:
    assert _is_number("3.14") is True
    assert _is_number("nope") is False
    assert _check_ip("10.0.0.1", version=4) is True
    assert _check_ip(12345, version=4) is False  # non-str
    assert _check_ip("not-an-ip", version=4) is False
    assert _check_decimal("1.50", "2") is True
    assert _check_decimal(True, "2") is False  # bool rejected
    assert _check_decimal("abc", "2") is False  # non-number
    assert _check_multiple_of(9, "3") is True
    assert _check_multiple_of("abc", "3") is False  # non-number
    assert _check_multiple_of(5, "0") is False  # zero divisor
