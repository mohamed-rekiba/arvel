"""``make:channel`` — generate a broadcast channel authorization callback.

Channels are async authorization callbacks registered against a Pusher-style
pattern (e.g. ``private-order.{order_id}``). The callback receives the
authenticated ``user`` plus each ``{placeholder}`` from the pattern as a
keyword argument, and returns either:

- ``bool`` — ``True`` to allow, ``False``/``None`` to reject; or
- ``dict[str, Any]`` — for a presence channel, the payload to broadcast
  alongside the subscription event.

Register the callback in a service provider's :meth:`boot` method.
"""

from __future__ import annotations

from typing import ClassVar

from arvel.console.commands._base_make import BaseMakeCommand
from arvel.support.str import Str

_TEMPLATE = '''"""{title} — broadcast channel authorization callback."""

from __future__ import annotations

from typing import Any

from arvel.facades.broadcast import Broadcast


@Broadcast.channel("private-{snake}.{{id}}")
async def authorize_{snake}(user: Any, id: str) -> bool:
    """Allow ``user`` to subscribe to ``private-{snake}.<id>``.

    Replace this with your own ownership check — e.g. compare ``user.id``
    against the row's owner column.
    """
    return getattr(user, "id", None) == int(id)
'''


def _channel_slug(name: str) -> str:
    return Str.snake(name).removesuffix("_channel")


class MakeChannelCommand(BaseMakeCommand):
    name: ClassVar[str] = "make:channel"
    help: ClassVar[str] = "Generate a broadcast channel authorization callback"
    _target_subdir: ClassVar[str] = "app/broadcasting/channels"
    _suffix: ClassVar[str] = "Channel"

    def _render(self, name: str) -> str:
        return _TEMPLATE.format(title=Str.pascal(name), snake=_channel_slug(name))
