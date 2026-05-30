"""``make:event`` — generate an immutable Pydantic event class.

Arvel events are frozen Pydantic models. Declare payload fields directly
on the subclass; the class auto-registers into ``EventRegistry`` so it
can be deserialized off the queue.

Mix in :class:`arvel.broadcasting.ShouldBroadcast` to broadcast the
event over WebSockets in addition to firing local listeners.
"""

from __future__ import annotations

from typing import ClassVar

from arvel.console.commands._base_make import BaseMakeCommand
from arvel.support.str import Str

_TEMPLATE = '''"""{title} — domain event."""

from __future__ import annotations

from arvel.events import Event


class {title}(Event):
    """Fired when something noteworthy happens in the domain."""

    # Declare payload fields here, e.g.:
    # user_id: int
    # email: str
'''


class MakeEventCommand(BaseMakeCommand):
    name: ClassVar[str] = "make:event"
    help: ClassVar[str] = "Generate a Pydantic event class"
    _target_subdir: ClassVar[str] = "app/events"

    def _render(self, name: str) -> str:
        return _TEMPLATE.format(title=Str.pascal(name))
