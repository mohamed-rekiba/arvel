"""Log redaction reaches into nested dicts and lists, not just top-level keys.

WI-019 made redaction substring-match top-level keys but left nested structures
untouched, so ``Log.info("login", payload={"password": ...})`` leaked the secret
because the top-level key (``payload``) isn't itself a secret. Redaction now
recurses to any depth, mirroring ``config._strip_secrets``. Exercised through the
public ``Log`` facade so it covers the real emit path.
"""

from __future__ import annotations

import pytest


class TestNestedRedaction:
    def test_secret_inside_nested_dict_is_redacted(self) -> None:
        from arvel.facades import Log
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            Log.info("login", payload={"password": "hunter2", "user": "alice"})

        record = next(r for r in obs.log_records if r.body == "login")
        assert record.attributes["payload"] == {"password": "[REDACTED]", "user": "alice"}

    def test_secret_deep_in_nested_dict_is_redacted(self) -> None:
        from arvel.facades import Log
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            Log.info("event", outer={"inner": {"api_key": "LEAK", "ok": 1}})

        record = next(r for r in obs.log_records if r.body == "event")
        assert record.attributes["outer"] == {"inner": {"api_key": "[REDACTED]", "ok": 1}}

    def test_secret_inside_list_of_dicts_is_redacted(self) -> None:
        from arvel.facades import Log
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            Log.info("batch", items=[{"access_token": "T", "name": "ok"}, {"name": "plain"}])

        record = next(r for r in obs.log_records if r.body == "batch")
        items = record.attributes["items"]
        assert list(items) == [{"access_token": "[REDACTED]", "name": "ok"}, {"name": "plain"}]

    def test_non_secret_nesting_passes_through(self) -> None:
        from arvel.facades import Log
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            Log.info("plain", meta={"route": "/orders", "tags": ["a", "b"]}, count=3)

        record = next(r for r in obs.log_records if r.body == "plain")
        # OTel normalizes leaf scalar sequences to tuples — compare structurally.
        meta = record.attributes["meta"]
        assert meta["route"] == "/orders"
        assert list(meta["tags"]) == ["a", "b"]
        assert record.attributes["count"] == 3

    def test_top_level_secret_still_redacted(self) -> None:
        from arvel.facades import Log
        from arvel.testing.observability import FakeObservability

        with FakeObservability() as obs:
            Log.info("auth", token="TOP", user="bob")

        record = next(r for r in obs.log_records if r.body == "auth")
        assert record.attributes["token"] == "[REDACTED]"
        assert record.attributes["user"] == "bob"

    def test_custom_redact_set_applies_to_nested_keys(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel.facades import Log
        from arvel.testing.observability import FakeObservability

        monkeypatch.setenv("LOG_REDACT_FIELDS", "pin")
        with FakeObservability() as obs:
            Log.info("payment", details={"card_pin": "1234", "name": "bob"})

        record = next(r for r in obs.log_records if r.body == "payment")
        assert record.attributes["details"] == {"card_pin": "[REDACTED]", "name": "bob"}
