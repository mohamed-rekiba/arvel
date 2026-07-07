"""arvel.http.flash — session flash + error bag.

A ``FlashBag`` over the request session stores one-request messages (``flash("status", ...)``)
and validation errors (``errors()``), read back on the next request and exposed to templates.

**Aging.** Each flash is marked *fresh* when written; ``StartSession``
calls ``age()`` at the **start** of every request, which drops anything that is no longer fresh
(it was already shown last request) and demotes the rest to stale. So a message flashed in request
*A* is visible in request *B* and gone by *C* — surviving exactly one request. Aging at request
*start* (not end) keeps it uniform whether the flash was written during the request (success path)
or **after** the session middleware's teardown (the error renderer's redirect-back path).
"""

from __future__ import annotations

from typing import Any, cast


class FlashBag:
    """Read/write transient session data (status messages, old input, validation errors)."""

    KEY = "_flash"
    ERRORS_KEY = "_errors"
    FRESH_KEY = "_flash_fresh"  # keys flashed this request; survive the next age()
    OLD_INPUT_KEY = "_old_input"

    def __init__(self, session: dict[str, Any]) -> None:
        self._session = session

    def _bag(self) -> dict[str, Any]:
        """The writable flash bag — created on demand (writes only; reads use ``_read_bag``)."""
        bag: dict[str, Any] = self._session.setdefault(self.KEY, {})
        return bag

    def _read_bag(self) -> dict[str, Any]:
        """The flash bag for reads — never mutates the session (so a read after ``age()`` doesn't
        re-create an empty ``_flash``)."""
        bag = self._session.get(self.KEY)
        return cast("dict[str, Any]", bag) if isinstance(bag, dict) else {}

    def _mark_fresh(self, key: str) -> None:
        fresh: list[str] = self._session.setdefault(self.FRESH_KEY, [])
        if key not in fresh:
            fresh.append(key)

    def flash(self, key: str, value: Any) -> FlashBag:
        self._bag()[key] = value
        self._mark_fresh(key)
        return self

    def get(self, key: str, default: Any = None) -> Any:
        return self._read_bag().get(key, default)

    def has(self, key: str) -> bool:
        return key in self._read_bag()

    def all(self) -> dict[str, Any]:
        return dict(self._read_bag())

    def flash_errors(self, errors: dict[str, list[str]]) -> FlashBag:
        self._session[self.ERRORS_KEY] = errors
        self._mark_fresh(self.ERRORS_KEY)
        return self

    def errors(self) -> dict[str, list[str]]:
        result: dict[str, list[str]] = self._session.get(self.ERRORS_KEY, {})
        return result

    def flash_input(self, data: dict[str, Any]) -> FlashBag:
        """Flash the request's input for one request. Stored as an ordinary
        flash entry, so the same aging expires it after the next request."""
        self.flash(self.OLD_INPUT_KEY, dict(data))
        return self

    def old(self, key: str | None = None, default: Any = None) -> Any:
        """Read flashed input. ``old()`` → all of it; ``old("field", d)`` → one
        value with a fallback. Empty when nothing was flashed."""
        raw = self._read_bag().get(self.OLD_INPUT_KEY)
        data: dict[str, Any] = cast("dict[str, Any]", raw) if isinstance(raw, dict) else {}
        if key is None:
            return dict(data)
        return data.get(key, default)

    def keep(self, keys: str | list[str]) -> FlashBag:
        """Re-flash only the named key(s) for one more request — ``.reflash()`` narrowed to
        specific keys. Marks each fresh again (the same bookkeeping :meth:`flash` uses), so the
        next :meth:`age` doesn't expire it; a name not currently in the bag is harmless (nothing to
        keep)."""
        for name in [keys] if isinstance(keys, str) else keys:
            self._mark_fresh(name)
        return self

    def reflash(self) -> FlashBag:
        """Re-flash ALL current flash data (and validation errors, if flashed) for exactly one
        more request — call it during a request whose flashed data should survive past the next
        :meth:`age` instead of expiring after this one."""
        self.keep(list(self._read_bag()))
        if self.ERRORS_KEY in self._session:
            self.keep(self.ERRORS_KEY)
        return self

    def age(self) -> None:
        """Drop flashes that are no longer fresh (shown last request), demoting the rest to stale.

        Run once per request at session load. Keeps anything (re)flashed during the previous request,
        expires everything older — the one-request flash lifecycle. Leaves no empty bookkeeping keys
        in the session (so callers that snapshot the session see only their own data)."""
        fresh = set(self._session.pop(self.FRESH_KEY, []))
        bag = self._session.get(self.KEY)
        if isinstance(bag, dict):
            bag_d = cast("dict[str, Any]", bag)
            for key in [k for k in bag_d if k not in fresh]:
                del bag_d[key]
            if not bag_d:
                self._session.pop(self.KEY, None)  # don't leave an empty _flash behind
        if self.ERRORS_KEY not in fresh:
            self._session.pop(self.ERRORS_KEY, None)

    def clear(self) -> None:
        self._session[self.KEY] = {}
        self._session.pop(self.ERRORS_KEY, None)
        self._session.pop(self.FRESH_KEY, None)
