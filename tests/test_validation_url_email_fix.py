"""Spec 12 A7 — `url`/`email` structural fixes.

Before: `url` was an `http(s)://`-prefix check (accepted `http://`, `http://x y`); `email` was a
loose `local@domain.tld` regex with no length caps. Table-driven fixture matrix, valid + invalid."""

from __future__ import annotations

import pytest

from arvel.validation import Validator

URL_CASES = [
    ("https://host/path?q=1", True),
    ("http://example.com", True),
    ("http://example.com:8080/a/b", True),
    ("https://sub.example.co.uk", True),
    ("notaurl", False),  # no scheme, no host
    ("http://", False),  # scheme but no host — this used to pass (prefix-only check)
    ("http://x y.com", False),  # embedded space
    ("javascript:alert(1)", False),  # disallowed scheme
    ("ftp://files.example.com", False),  # not in the default {http, https} set
]


@pytest.mark.parametrize(("value", "expected"), URL_CASES)
def test_url_matrix(value: str, expected: bool) -> None:
    assert Validator({"u": value}, {"u": "url"}).passes() is expected


def test_url_custom_scheme_arg() -> None:
    assert Validator({"u": "ftp://files.example.com"}, {"u": "url:http,https,ftp"}).passes()
    assert not Validator({"u": "https://x.com"}, {"u": "url:ftp"}).passes()


EMAIL_CASES = [
    ("a.b+t@ex.co", True),
    ("ada@example.com", True),
    ("a@", False),  # no domain
    ("a@b", False),  # no TLD
    ("a b@c.com", False),  # embedded space
    ("a..b@example.com", False),  # consecutive dots in local part
    ("a@example..com", False),  # consecutive dots in domain
    (".a@example.com", False),  # leading dot in local part
    ("a.@example.com", False),  # trailing dot in local part
    ("a" * 65 + "@example.com", False),  # local part over the 64-char cap
    ("a@" + "b" * 300 + ".com", False),  # domain over the 255-char cap
]


@pytest.mark.parametrize(("value", "expected"), EMAIL_CASES)
def test_email_matrix(value: str, expected: bool) -> None:
    assert Validator({"e": value}, {"e": "email"}).passes() is expected


def test_no_active_url_rule() -> None:
    # spec A7: active_url (DNS lookup) is deliberately NOT ported — no such rule exists; a typo'd
    # or intentionally-unsupported name is a lenient no-op in the default (non-strict) mode.
    assert Validator({"u": "https://x.com"}, {"u": "active_url"}).passes()
