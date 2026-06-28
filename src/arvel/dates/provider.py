"""DateServiceProvider — binds ``date`` (root of the Date facade).

The Date facade proxies to the :class:`~arvel.dates.Date` class, whose classmethods
(``now``/``today``/``parse``) are the Laravel ``Date`` factory surface. The root ``arvel.Date``
remains the class itself (ergonomic + ``isinstance``-friendly); the facade is the formal
Facade-pattern accessor over the same ``date`` binding.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.dates import Date
from arvel.kernel.service_provider import ServiceProvider

if TYPE_CHECKING:
    from arvel.contracts import Container


class DateServiceProvider(ServiceProvider):
    def register(self) -> None:
        def make_date(_app: Container) -> type[Date]:
            return Date

        self.app.singleton("date", make_date)

    def boot(self) -> None:
        """No-op."""
