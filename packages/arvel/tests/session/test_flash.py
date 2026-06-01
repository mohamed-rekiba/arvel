"""Tests for FlashBag."""

from __future__ import annotations

from arvel.session import SessionData


class TestFlashBag:
    """Flash values are read once on the next request."""

    def test_flash_is_not_readable_on_same_request(self) -> None:
        session = SessionData(data={})
        session.flash("status", "Saved!")
        # Flash new — not in the old bucket yet
        assert session.get("status") is None

    def test_flash_readable_after_finalize(self) -> None:
        session = SessionData(data={})
        session.flash("status", "Saved!")
        session.finalize_flash()  # simulates request transition
        assert session.get("status") == "Saved!"

    def test_flash_consumed_after_second_finalize(self) -> None:
        session = SessionData(data={})
        session.flash("status", "Saved!")
        session.finalize_flash()  # new → old
        session.finalize_flash()  # old cleared
        assert session.get("status") is None

    def test_reflash_keeps_old_flash_for_one_more_request(self) -> None:
        session = SessionData(data={})
        session.flash("status", "Saved!")
        session.finalize_flash()  # new → old; status is readable
        session.reflash()  # re-promotes old → new (keeps it alive)
        session.finalize_flash()  # new → old again
        assert session.get("status") == "Saved!"

    def test_now_available_only_current_request(self) -> None:
        session = SessionData(data={})
        session.now("temp", "current-only")
        # Available before finalize
        assert session.get("temp") == "current-only"
        # Gone after finalize (it's in old bucket, which gets cleared)
        session.finalize_flash()
        session.finalize_flash()
        assert session.get("temp") is None

    def test_multiple_flash_keys(self) -> None:
        session = SessionData(data={})
        session.flash("success", "Done!")
        session.flash("error", None)  # None is a valid flash value
        session.finalize_flash()
        assert session.get("success") == "Done!"

    def test_flash_does_not_overwrite_regular_data(self) -> None:
        session = SessionData(data={"user_id": 42})
        session.flash("status", "OK")
        assert session.get("user_id") == 42
