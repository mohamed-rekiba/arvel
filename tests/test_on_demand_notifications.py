"""On-demand notifications: send to an ad-hoc recipient with no stored model via
``AnonymousNotifiable().route(channel, route)``."""

from __future__ import annotations

from typing import Any

from arvel.mail import Mailable, MailManager
from arvel.notifications import AnonymousNotifiable, Notification, NotificationManager


class _Welcome(Mailable):
    def build(self) -> Mailable:
        return self.subject("Hi").html("<p>hi</p>")


class _WelcomeNotification(Notification):
    def via(self, notifiable: Any) -> list[str]:
        return ["mail", "database"]

    def to_mail(self, notifiable: Any) -> Mailable:
        return _Welcome()

    def to_array(self, notifiable: Any) -> dict[str, Any]:
        return {"message": "welcome"}

    def apprise_urls(self, notifiable: Any) -> list[str]:
        return ["json://fallback.example"]


def test_anonymous_notifiable_routes_are_chainable_and_read_back() -> None:
    anon = AnonymousNotifiable().route("mail", "ops@acme.test").route("slack", "json://hook")
    assert anon.route_notification_for("mail") == "ops@acme.test"
    assert anon.route_notification_for("slack") == "json://hook"
    assert anon.route_notification_for("sms") is None  # unset channel


def test_route_falls_back_to_default_for_a_plain_notifiable() -> None:
    # no route_notification_for on this notifiable → the default is used
    assert (
        NotificationManager._route("ada@example.com", "mail", "ada@example.com")
        == "ada@example.com"
    )
    # apprise channel: anonymous route wins over the notification's apprise_urls
    anon = AnonymousNotifiable().route("slack", "json://hook")
    assert NotificationManager._route(anon, "slack", None) == "json://hook"


async def test_on_demand_mail_delivers_to_the_routed_address() -> None:
    from arvel.kernel import Application, set_application

    app = Application()
    app.instance("mail", MailManager(app))  # log driver by default — inspectable
    app.instance("notifications", NotificationManager(app))
    set_application(app)
    try:
        results = (
            await AnonymousNotifiable()
            .route("mail", "ops@acme.test")
            .notify(_WelcomeNotification())
        )
        assert set(results) == {"mail", "database"}
        sent = app.make("mail").transport().sent
        assert sent[-1]["To"] == "ops@acme.test"  # routed to the on-demand address, not a model
    finally:
        set_application(None)


async def test_on_demand_apprise_route_accepts_a_bare_url_string(monkeypatch: Any) -> None:
    """The docs' on-demand example registers ONE url string: `.route("slack", "json://...")`.
    Iterating that string character-by-character added no valid URL and silently dropped the
    send — a bare string must behave exactly like a one-element list."""

    class _SpyApprise:
        def __init__(self) -> None:
            self.added: list[str] = []

        def add(self, url: str) -> bool:
            self.added.append(url)
            return True

        async def async_notify(self, **kwargs: Any) -> bool:
            return bool(self.added)

    spy = _SpyApprise()
    manager = NotificationManager()
    monkeypatch.setattr(manager, "apprise", lambda: spy)

    class _Ping(Notification):
        def via(self, notifiable: Any) -> list[str]:
            return ["slack"]

    anon = AnonymousNotifiable().route("slack", "json://hooks.example/team")
    results = await manager.send_now(anon, _Ping())

    assert spy.added == ["json://hooks.example/team"]  # the URL, never its characters
    assert results["slack"] is True
