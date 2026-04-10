"""MailFake — testing double that captures sent mailables for assertion."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.mail.contracts import MailContract

if TYPE_CHECKING:
    from arvel.mail.mailable import Mailable


class MailFake(MailContract):
    """Captures all sent mailables for test assertions."""

    def __init__(self) -> None:
        self._sent: list[Mailable] = []

    @property
    def sent_count(self) -> int:
        return len(self._sent)

    async def send(self, mailable: Mailable) -> None:
        self._sent.append(mailable)

    def assert_sent(self, **kwargs: str) -> None:
        for m in self._sent:
            if all(getattr(m, k, None) == v for k, v in kwargs.items()):
                return
        msg = f"Expected mailable with {kwargs} to be sent, but no match found"
        raise AssertionError(msg)

    def assert_nothing_sent(self) -> None:
        if self._sent:
            msg = f"Expected no emails sent, but got {len(self._sent)}"
            raise AssertionError(msg)

    def assert_sent_to(self, address: str) -> None:
        for m in self._sent:
            if address in m.to:
                return
        msg = f"Expected email sent to '{address}', but no match found"
        raise AssertionError(msg)

    def assert_not_sent(self, **kwargs: str) -> None:
        for m in self._sent:
            if all(getattr(m, k, None) == v for k, v in kwargs.items()):
                msg = f"Expected mailable with {kwargs} not to be sent, but it was"
                raise AssertionError(msg)

    def assert_sent_count(self, expected: int) -> None:
        actual = len(self._sent)
        if actual != expected:
            msg = f"Expected {expected} emails sent, but got {actual}"
            raise AssertionError(msg)
