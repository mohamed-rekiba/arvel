"""FR-001-011: Contextual bindings."""

from __future__ import annotations


class IMailer:
    name: str = "default"


class SmtpMailer(IMailer):
    name = "smtp"


class SesMailer(IMailer):
    name = "ses"


class TransactionalNotifier:
    def __init__(self, mailer: IMailer) -> None:
        self.mailer = mailer


class MarketingNotifier:
    def __init__(self, mailer: IMailer) -> None:
        self.mailer = mailer


def test_contextual_binding_applies_to_specific_consumer() -> None:
    from arvel.container import Container

    c = Container()
    c.bind(IMailer, SmtpMailer)
    c.when(MarketingNotifier).needs(IMailer).give(SesMailer)

    tx = c.make(TransactionalNotifier)
    mk = c.make(MarketingNotifier)
    assert isinstance(tx.mailer, SmtpMailer)
    assert isinstance(mk.mailer, SesMailer)


def test_contextual_with_callable() -> None:
    from arvel.container import Container

    c = Container()
    c.bind(IMailer, SmtpMailer)
    c.when(MarketingNotifier).needs(IMailer).give(lambda: SesMailer())

    mk = c.make(MarketingNotifier)
    assert isinstance(mk.mailer, SesMailer)


def test_contextual_with_instance() -> None:
    from arvel.container import Container

    sentinel = SesMailer()
    c = Container()
    c.bind(IMailer, SmtpMailer)
    c.when(MarketingNotifier).needs(IMailer).give(sentinel)

    mk = c.make(MarketingNotifier)
    assert mk.mailer is sentinel
