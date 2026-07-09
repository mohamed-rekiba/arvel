"""arvel.http.redirect — the fluent ``Redirect`` value.

A ``Redirect`` carries where to go plus what to flash; the response-conversion funnel
(``arvel.http.responder.to_response``) turns it into a 302 (or the given status) and writes the
flash/old-input/errors through the **same** session machinery ``ShareErrorsFromSession`` and
``render_exception``'s redirect-back path already use (``arvel.http.flash.FlashBag``,
``Request._flash_old_input``) — no second flash implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass
class Redirect:
    location: str | None = None
    status: int = 302
    headers: dict[str, str] = field(default_factory=dict[str, str])
    flash_data: dict[str, Any] = field(default_factory=dict[str, Any])
    errors: dict[str, list[str]] | None = None
    wants_input: bool = False
    input_except: tuple[str, ...] = ()

    def route(self, name: str, **params: Any) -> Redirect:
        """Redirect to a named route; resolved through the
        app's bound ``router`` (the container path — http sits below routing in the DAG, so this
        can't import ``arvel.routing`` directly, same as ``ValidateSignature``)."""
        from arvel.kernel import app

        self.location = app("router").url(name, **params)
        return self

    def away(self, url: str) -> Redirect:
        """Redirect to an arbitrary (possibly off-site) URL — no same-origin check, unlike
        :meth:`back`."""
        self.location = url
        return self

    def back(self, fallback: str = "/") -> Redirect:
        """Redirect to the ``Referer``, or ``fallback`` when
        there's no active request or no (safe) Referer. Reuses the same same-origin-or-root guard
        ``render_exception``'s redirect-back path uses, so a crafted ``Referer`` can't open-redirect."""
        from arvel.http.exceptions import same_origin_or_root
        from arvel.http.request import current_request

        request = current_request.get(None)
        self.location = fallback
        if request is not None:
            raw = request.header("referer") or request.header("referrer")
            if raw:
                host = request.header("host") or ""
                self.location = same_origin_or_root(raw, host)
        return self

    def with_(self, key: str, value: Any) -> Redirect:
        """Flash one ``key``/``value`` for the next request."""
        self.flash_data[key] = value
        return self

    def with_input(self, *, except_: Sequence[str] = ()) -> Redirect:
        """Flash the current request's input for form repopulation;
        ``except_`` adds fields to skip on top of the always-excluded password fields
        (``Request._DONT_FLASH``). Reading the input itself happens at conversion time (the kernel
        already has the request in an async context)."""
        self.wants_input = True
        self.input_except = tuple(except_)
        return self

    def with_errors(self, bag: dict[str, list[str]]) -> Redirect:
        """Flash a validation error bag, read back via
        ``ShareErrorsFromSession``/``$errors`` on the next request."""
        self.errors = bag
        return self


def redirect(to: str | None = None) -> Redirect:
    """Start a fluent redirect."""
    return Redirect(location=to)
