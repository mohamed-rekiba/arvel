"""Log redaction matches secret-bearing keys by substring, not exact name.

A redact hint like ``token`` must also catch ``access_token`` / ``refresh_token``;
``secret`` must catch ``client_secret``; ``password`` must catch ``db_password``.
Exact-match redaction silently leaked these to logs. Exercised through the
public ``Log`` facade so it covers the real emit path.
"""

from __future__ import annotations

import pytest

_LEAKY_KEYS = (
    "access_token",
    "refresh_token",
    "client_secret",
    "api_secret",
    "db_password",
    "proxy_authorization",
)


class TestRedactSubstring:
    @pytest.mark.parametrize("field", _LEAKY_KEYS)
    def test_secret_substring_keys_are_redacted(self, field: str) -> None:
        from arvel.facades import Log
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            Log.info("secret.event", **{field: "LEAK", "username": "alice"})

        record = next(r for r in obs.log_records if r.body == "secret.event")
        assert record.attributes.get(field) == "[REDACTED]", f"{field!r} leaked"
        assert record.attributes.get("username") == "alice"

    def test_non_secret_keys_pass_through(self) -> None:
        from arvel.facades import Log
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            Log.info("plain.event", user_id=42, route="/orders", count=3)

        record = next(r for r in obs.log_records if r.body == "plain.event")
        assert record.attributes.get("user_id") == 42
        assert record.attributes.get("route") == "/orders"
        assert record.attributes.get("count") == 3

    def test_custom_redact_set_is_substring_matched(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from arvel.facades import Log
        from arvel.testing.observability import FakeObservability

        monkeypatch.setenv("LOG_REDACT_FIELDS", "pin")
        with FakeObservability() as obs:
            Log.info("payment.event", card_pin="1234", name="bob")

        record = next(r for r in obs.log_records if r.body == "payment.event")
        assert record.attributes.get("card_pin") == "[REDACTED]"
        assert record.attributes.get("name") == "bob"
