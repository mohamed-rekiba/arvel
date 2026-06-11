"""Tests for SessionData."""

from __future__ import annotations

from arvel.session import SessionData


class TestSessionDataBasicOps:
    def test_get_existing_key(self, session_with_data: SessionData) -> None:
        assert session_with_data.get("user_id") == 42

    def test_get_missing_returns_none(self, empty_session: SessionData) -> None:
        assert empty_session.get("missing") is None

    def test_get_with_default(self, empty_session: SessionData) -> None:
        assert empty_session.get("missing", default="fallback") == "fallback"

    def test_put_stores_value(self, empty_session: SessionData) -> None:
        empty_session.put("key", "value")
        assert empty_session.get("key") == "value"

    def test_has_true(self, session_with_data: SessionData) -> None:
        assert session_with_data.has("user_id") is True

    def test_has_false(self, empty_session: SessionData) -> None:
        assert empty_session.has("missing") is False

    def test_forget_removes_key(self, session_with_data: SessionData) -> None:
        session_with_data.forget("user_id")
        assert session_with_data.has("user_id") is False

    def test_flush_clears_all(self, session_with_data: SessionData) -> None:
        session_with_data.flush()
        assert session_with_data.all() == {}

    def test_all_returns_dict(self, session_with_data: SessionData) -> None:
        data = session_with_data.all()
        assert "user_id" in data
        assert "name" in data


class TestSessionDataRegenerate:
    def test_regenerate_changes_session_id(self, empty_session: SessionData) -> None:
        old_id = empty_session.get_id()
        empty_session.regenerate()
        new_id = empty_session.get_id()
        assert old_id != new_id

    def test_regenerate_preserves_data(self, session_with_data: SessionData) -> None:
        session_with_data.regenerate()
        assert session_with_data.get("user_id") == 42

    def test_regenerate_queues_old_id_for_destruction(self, session_with_data: SessionData) -> None:
        old_id = session_with_data.get_id()
        session_with_data.regenerate()
        assert session_with_data.drain_pending_destroy() == [old_id]

    def test_drain_pending_destroy_is_one_shot(self, empty_session: SessionData) -> None:
        empty_session.regenerate()
        assert len(empty_session.drain_pending_destroy()) == 1
        assert empty_session.drain_pending_destroy() == []

    def test_pending_destroy_not_serialized(self, session_with_data: SessionData) -> None:
        session_with_data.regenerate()
        assert "_pending_destroy" not in session_with_data.to_dict()


class TestSessionDataInvalidate:
    def test_invalidate_clears_data(self, session_with_data: SessionData) -> None:
        session_with_data.invalidate()
        assert session_with_data.all() == {}

    def test_invalidate_rotates_id_and_queues_old(self, session_with_data: SessionData) -> None:
        old_id = session_with_data.get_id()
        session_with_data.invalidate()
        assert session_with_data.get_id() != old_id
        assert session_with_data.drain_pending_destroy() == [old_id]


class TestSessionDataCsrfToken:
    def test_token_is_stable_within_session(self, empty_session: SessionData) -> None:
        first = empty_session.token()
        assert first
        assert empty_session.token() == first

    def test_regenerate_token_rotates(self, empty_session: SessionData) -> None:
        first = empty_session.token()
        empty_session.regenerate_token()
        assert empty_session.token() != first

    def test_token_not_exposed_via_all(self, empty_session: SessionData) -> None:
        empty_session.token()
        assert "_csrf_token" not in empty_session.all()


class TestSessionDataSerialization:
    def test_to_dict_and_from_dict(self, session_with_data: SessionData) -> None:
        serialized = session_with_data.to_dict()
        restored = SessionData.from_dict(serialized)
        assert restored.get("user_id") == 42
        assert restored.get("name") == "Alice"
