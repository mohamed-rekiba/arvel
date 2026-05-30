"""Shared fixtures for notifications tests."""

from __future__ import annotations

from typing import Any

import pytest
from arvel.mail.content import Content
from arvel.mail.envelope import Envelope
from arvel.mail.mailable import Mailable
from arvel.notifications.notification import Notification


class FakeUser:
    def __init__(self, user_id: int, email: str = "user@example.com") -> None:
        self.id = user_id
        self.email = email


class WelcomeMail(Mailable):
    def envelope(self) -> Envelope:
        return Envelope(
            from_address="no-reply@example.com",
            to=["user@example.com"],
            subject="Welcome!",
        )

    def content(self) -> Content:
        return Content(text="Welcome!")


class WelcomeNotification(Notification):
    def via(self, notifiable: Any) -> list[str]:
        return ["mail", "database", "log"]

    def to_mail(self, notifiable: Any) -> Mailable:
        return WelcomeMail()

    def to_database(self, notifiable: Any) -> dict[str, Any]:
        return {"action": "welcome", "user_id": notifiable.id}


class DbOnlyNotification(Notification):
    def via(self, notifiable: Any) -> list[str]:
        return ["database"]

    def to_database(self, notifiable: Any) -> dict[str, Any]:
        return {"action": "db_only"}


@pytest.fixture
def fake_user() -> FakeUser:
    return FakeUser(user_id=42)
