"""MailServiceProvider — binds the Mail manager (auto-discovered)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.kernel.service_provider import ServiceProvider
from arvel.mail import MailManager

if TYPE_CHECKING:
    from arvel.contracts import Container


class MailServiceProvider(ServiceProvider):
    def register(self) -> None:
        def make_mail(app: Container) -> MailManager:
            return MailManager(app)

        self.app.singleton("mail", make_mail)

    def boot(self) -> None:
        """No-op."""
