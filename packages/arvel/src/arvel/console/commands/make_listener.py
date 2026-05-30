"""``make:listener`` — generate an event listener bound to an Event subclass.

Listeners subclass :class:`arvel.events.Listener` parameterised by the
event they react to. ``Listener[E]`` is generic — substitute ``E`` with
your own ``Event`` subclass and the type checker will enforce that the
``handle`` body sees the right payload.

Wire listeners up with ``dispatcher.listen(MyEvent, MyListener)`` in a
service provider's :meth:`boot` method. Mix in
:class:`arvel.events.ShouldQueue` to run the listener as a queued job
instead of in-process.
"""

from __future__ import annotations

from typing import ClassVar

from arvel.console.commands._base_make import BaseMakeCommand
from arvel.support.str import Str

_TEMPLATE = '''"""{title} — event listener."""

from __future__ import annotations

from arvel.events import Event, Listener


class {title}(Listener[Event]):
    """React to a domain event.

    Swap ``Event`` for your specific event class (e.g. ``UserRegistered``)
    so the type checker can validate the handler body.
    """

    async def handle(self, event: Event) -> None:
        """Process the event. Raise to mark the listener as failed."""
'''


class MakeListenerCommand(BaseMakeCommand):
    name: ClassVar[str] = "make:listener"
    help: ClassVar[str] = "Generate an event listener (Listener[E] + async handle)"
    _target_subdir: ClassVar[str] = "app/listeners"

    def _render(self, name: str) -> str:
        return _TEMPLATE.format(title=Str.pascal(name))
