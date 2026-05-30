"""FlashBag wrapper coverage."""

from __future__ import annotations

from arvel.session import SessionData
from arvel.session.flash import FlashBag


def test_flash_bag_delegates_to_session_data() -> None:
    session = SessionData(data={})
    flash = FlashBag(session)

    flash.flash("status", "saved")
    session.finalize_flash()
    assert flash.has("status") is True
    assert flash.get("status") == "saved"

    flash.reflash()
    session.finalize_flash()
    assert flash.get("status") == "saved"

    flash.now("inline", "now")
    assert flash.get("inline") == "now"
    assert flash.get("missing", "fallback") == "fallback"
