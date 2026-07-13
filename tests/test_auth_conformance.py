"""Auth conformance: EmailVerified event, truthy verified semantics, typed
signer errors, and UUID-safe verification ids."""

from __future__ import annotations

import pytest

from arvel.auth import Authenticatable, EmailVerified
from arvel.auth.flows import email_verification_token, verify_email_token
from arvel.security import SignatureInvalid, Signer

SIG = "test-secret"


class FakeUser(Authenticatable):
    def __init__(self, verified_at: object = None) -> None:
        self.email = "u@x"
        self.email_verified_at = verified_at
        self.saved = False

    async def save(self) -> bool:
        self.saved = True
        return True


def test_falsy_but_set_timestamp_is_not_verified() -> None:
    assert FakeUser(verified_at="").has_verified_email() is False
    assert FakeUser(verified_at=0).has_verified_email() is False
    assert FakeUser(verified_at="2026-01-01").has_verified_email() is True


async def test_mark_email_as_verified_dispatches_event_once() -> None:
    from arvel.events.dispatcher import Dispatcher
    from arvel.kernel.application import Application
    from arvel.kernel.globals import set_application

    seen: list[EmailVerified] = []
    app = Application()
    dispatcher = Dispatcher()
    dispatcher.listen(EmailVerified, lambda e: seen.append(e))
    app.instance("events", dispatcher)
    set_application(app)
    try:
        user = FakeUser()
        assert await user.mark_email_as_verified() is True
        assert await user.mark_email_as_verified() is False  # already verified → no re-fire
        assert len(seen) == 1 and seen[0].email == "u@x"
    finally:
        set_application(None)


def test_signer_raises_module_error_not_third_party() -> None:
    signer = Signer("secret")
    token = signer.sign("value")
    assert signer.unsign(token) == "value"
    with pytest.raises(SignatureInvalid):
        signer.unsign(token + "tampered")
    with pytest.raises(SignatureInvalid):
        Signer("other-secret").unsign(token)


def test_verification_ids_survive_uuid_keys() -> None:
    uid = "0189f1e2-abcd-7000-8000-000000000000"
    token = email_verification_token(uid, "u@x", SIG)
    assert verify_email_token(token, "u@x", SIG) == uid
