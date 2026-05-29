"""FR-001-012: Tagged bindings."""

from __future__ import annotations


class Channel:
    name: str = "?"


class SmsChannel(Channel):
    name = "sms"


class EmailChannel(Channel):
    name = "email"


class SlackChannel(Channel):
    name = "slack"


def test_tagged_returns_instances_in_registration_order() -> None:
    from arvel.container import Container

    c = Container()
    c.bind(SmsChannel)
    c.bind(EmailChannel)
    c.bind(SlackChannel)
    c.tag([SmsChannel, EmailChannel, SlackChannel], "notification.channels")

    out = c.tagged("notification.channels")
    names = [getattr(o, "name", None) for o in out]
    assert names == ["sms", "email", "slack"]


def test_tagged_returns_empty_list_for_unknown_tag() -> None:
    from arvel.container import Container

    c = Container()
    assert c.tagged("nope") == []


def test_tagged_instances_are_resolved_via_container() -> None:
    """Each tagged abstract gets full container resolution (so its deps are injected)."""
    from arvel.container import Container

    class Logger:
        def __init__(self) -> None: ...

    class AlertA:
        def __init__(self, logger: Logger) -> None:
            self.logger = logger

    class AlertB:
        def __init__(self, logger: Logger) -> None:
            self.logger = logger

    c = Container()
    c.singleton(Logger)
    c.bind(AlertA)
    c.bind(AlertB)
    c.tag([AlertA, AlertB], "alerts")

    alerts = c.tagged("alerts")
    assert len(alerts) == 2
    assert all(isinstance(a.logger, Logger) for a in alerts)
