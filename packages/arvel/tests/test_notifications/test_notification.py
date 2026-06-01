"""Tests for Notification base class."""

from __future__ import annotations

import pytest
from arvel.notifications.notification import Notification


class TestNotification:
    def test_notification_is_abstract(self) -> None:
        cls: type = Notification
        with pytest.raises(TypeError):
            cls()

    def test_via_must_be_implemented(self) -> None:
        class N(Notification):
            pass

        cls: type = N
        with pytest.raises(TypeError):
            cls()

    def test_concrete_notification_via(self) -> None:
        from .helpers import FakeUser, WelcomeNotification

        n = WelcomeNotification()
        user = FakeUser(1)
        assert n.via(user) == ["mail", "database", "log"]

    def test_to_mail_returns_mailable(self) -> None:
        from arvel.mail.mailable import Mailable

        from .helpers import FakeUser, WelcomeNotification

        n = WelcomeNotification()
        result = n.to_mail(FakeUser(1))
        assert isinstance(result, Mailable)

    def test_to_database_returns_dict(self) -> None:
        from .helpers import FakeUser, WelcomeNotification

        n = WelcomeNotification()
        result = n.to_database(FakeUser(1))
        assert isinstance(result, dict)
        assert result["action"] == "welcome"

    def test_default_to_mail_returns_none(self) -> None:
        from .helpers import DbOnlyNotification, FakeUser

        n = DbOnlyNotification()
        assert n.to_mail(FakeUser(1)) is None

    def test_default_to_database_returns_empty_dict(self) -> None:
        class LogOnly(Notification):
            def via(self, notifiable: object) -> list[str]:
                return ["log"]

        n = LogOnly()
        assert n.to_database(object()) == {}
