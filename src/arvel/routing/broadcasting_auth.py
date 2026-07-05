"""arvel.routing.broadcasting_auth — the ``/broadcasting/auth`` endpoint (Pusher-protocol channel
authorization).

Lives in **routing**, not ``arvel.broadcasting``: the handler needs BOTH the authenticated user
(``arvel.auth``) and the registered channel-authorization callbacks (``arvel.broadcasting``'s
``BroadcastManager``) — and broadcasting sits well below auth in the module DAG (G1), so it must
never import it. Routing is the top layer, so it can see both without either importing the other;
``RoutingServiceProvider`` wires this handler onto the route (behind ``Authenticate`` — a guest
never reaches a callback with ``user=None``). Grounded in projects/arvel/specs/19-msg-broadcast.md
§1.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from arvel.http.exceptions import abort
from arvel.http.response import Response


def _broadcast_manager(app: Any) -> Any:
    """The app's bound ``broadcast`` manager, else a fresh one (no channels registered — every
    channel then denies, same observable behaviour as an app that registered none)."""
    if app is not None and hasattr(app, "bound") and app.bound("broadcast"):
        return app.make("broadcast")
    from arvel.broadcasting import BroadcastManager

    return BroadcastManager(app)


def _sign(channel_name: str, socket_id: str, secret: str) -> str:
    """An HMAC-SHA256 signature over ``socket_id:channel_name``, keyed by ``app.key`` (Pusher
    private/presence channel auth parity — proves this server-side callback authorized the pair,
    without exposing the secret itself)."""
    return hmac.new(
        secret.encode(), f"{socket_id}:{channel_name}".encode(), hashlib.sha256
    ).hexdigest()


async def broadcasting_auth(request: Any) -> Response:
    """Resolve ``request``'s authenticated user + the requested channel, run its registered
    authorization callback, and return the auth signature (private) or member data (presence).
    403 when the callback denies or no pattern matches."""
    from arvel.kernel import app, has_application

    form = await request.form()
    channel_name = str(form.get("channel_name") or "")
    socket_id = str(form.get("socket_id") or "")
    user = request.user()

    current_app = app() if has_application() else None
    outcome = await _broadcast_manager(current_app).authorize(channel_name, user)
    if outcome is False:
        abort(403)

    secret = str(current_app.config("app.key") or "") if current_app is not None else ""
    if not secret:
        # an HMAC keyed with "" is forgeable — refuse to hand out a weak signature under a
        # misconfigured (empty) APP_KEY rather than emit one
        abort(500, "broadcasting auth requires a non-empty app.key")
    payload: dict[str, Any] = {"auth": _sign(channel_name, socket_id, secret)}
    if isinstance(outcome, dict):
        payload["channel_data"] = outcome
    return Response(content=payload)


__all__ = ["broadcasting_auth"]
