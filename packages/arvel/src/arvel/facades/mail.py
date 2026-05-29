"""Mail facade — classmethod API proxying to the bound Mailer (FR-009-020)."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Self

from arvel.queue.exceptions import FacadeNotBoundError

if TYPE_CHECKING:
    from arvel.mail.drivers.array import ArrayMailDriver
    from arvel.mail.mailer import MailDriver, Mailer
    from arvel.mail.pending_send import MailPendingSend
    from arvel.mail.rendered_mail import RenderedMail


class Mail:
    """Facade for the mail subsystem.

    Bound by ``MailServiceProvider.boot()``.
    Use ``Mail.fake()`` in tests to capture sent mail.
    """

    _mailer: ClassVar[Mailer | None] = None

    @classmethod
    def bind(cls, mailer: Mailer) -> None:
        cls._mailer = mailer

    @classmethod
    def reset(cls) -> None:
        """Unbind the mailer. Call in test teardown to avoid state leakage."""
        cls._mailer = None

    @classmethod
    def get_mailer(cls) -> Mailer:
        if cls._mailer is None:
            raise FacadeNotBoundError("Mail")
        return cls._mailer

    @classmethod
    def to(cls, address: object) -> MailPendingSend:
        """Begin a fluent send chain."""
        return cls.get_mailer().to(address)

    @classmethod
    def fake(cls) -> _FakeContext:
        """Swap the active driver to ArrayMailDriver immediately and return a context manager.

        Swaps the driver on call so you can use it without ``with``.
        Also supports ``with Mail.fake() as driver:`` — restores the original driver on exit.

        Usage::

            # Direct usage:
            driver = Mail.fake()
            await Mail.to("a@b.com").send(MyMail())
            assert len(driver.sent) == 1

            # Context manager (restores original driver):
            with Mail.fake() as driver:
                await Mail.to("a@b.com").send(MyMail())
                assert len(driver.sent) == 1
        """
        from arvel.mail.drivers.array import ArrayMailDriver

        mailer = cls.get_mailer()
        fake_driver = ArrayMailDriver()
        original = mailer.swap_driver(fake_driver)
        return _FakeContext(fake_driver, mailer, original)


class _FakeContext:
    """Returned by ``Mail.fake()``. Context manager that restores the original mail driver."""

    def __init__(self, driver: ArrayMailDriver, mailer: Mailer, original: MailDriver) -> None:
        self._driver = driver
        self._mailer = mailer
        self._original = original

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self._mailer.swap_driver(self._original)

    @property
    def sent(self) -> list[RenderedMail]:
        return self._driver.sent

    def reset(self) -> None:
        self._driver.reset()


__all__ = ["Mail"]
