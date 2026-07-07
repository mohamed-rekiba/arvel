"""arvel.activitylog — an activity log / audit trail, modelled on the Spatie-style activitylog.

Two ways in:
- ``activity()`` — a fluent logger for *any* event: ``await activity().caused_by(user)
.performed_on(post).with_properties({...}).log("approved")``.
- the ``LogsActivity`` model mixin — auto-logs every create/update/delete of a model, capturing
  the changed attributes (``{old, attributes}``) in the activity's ``properties``. That auto-log
  *is* the audit trail; ``activity()`` is the broader event stream around it.

Activities are rows in the ``activity_log`` table (the:class:`Activity` model). Not part of the
original ch-08 port spec — added on request, following the Spatie design.
"""

from __future__ import annotations

from typing import Any, ClassVar, cast

from arvel.contracts import ModelHost
from arvel.database import Model


class Activity(Model):
    """A single logged activity (row in ``activity_log``)."""

    __table_name__ = "activity_log"
    __fields__: ClassVar[dict[str, Any]] = {
        "log_name": str,
        "description": str,
        "subject_type": str,
        "subject_id": int,
        "causer_type": str,
        "causer_id": int,
        "event": str,
        "properties": dict,
        "batch_uuid": str,
    }
    __fillable__: ClassVar[list[str]] = list(__fields__)
    __casts__: ClassVar[dict[str, str]] = {"properties": "json"}

    def changes(self) -> dict[str, Any]:
        """The recorded change set — ``{"old": {...}, "attributes": {...}}`` for model events."""
        raw = self.properties
        props: dict[str, Any] = cast("dict[str, Any]", raw) if isinstance(raw, dict) else {}
        return {k: props[k] for k in ("old", "attributes") if k in props}


def _identify(thing: Any) -> tuple[str | None, Any]:
    """A ``(type_name, primary_key)`` pair for a model instance (or ``(None, None)``)."""
    if thing is None:
        return None, None
    pk_name = cast("str", getattr(thing, "__primary_key__", "id"))
    from arvel.database import morph_type_of

    return morph_type_of(type(thing)), getattr(thing, pk_name, None)


class ActivityLogger:
    """Fluent builder for one activity — terminated by ``log(description)``."""

    def __init__(self, log_name: str = "default") -> None:
        self._log_name = log_name
        self._description: str = ""
        self._subject: Any = None
        self._causer: Any = None
        self._event: str | None = None
        self._properties: dict[str, Any] = {}

    def use_log(self, log_name: str) -> ActivityLogger:
        self._log_name = log_name
        return self

    def performed_on(self, subject: Any) -> ActivityLogger:
        """The subject the activity is *about* (Spatie ``performedOn`` / ``on``)."""
        self._subject = subject
        return self

    on = performed_on

    def caused_by(self, causer: Any) -> ActivityLogger:
        """Who caused the activity (Spatie ``causedBy`` / ``by``). Defaults to the auth user."""
        self._causer = causer
        return self

    by = caused_by

    def with_properties(self, properties: dict[str, Any]) -> ActivityLogger:
        self._properties = dict(properties)
        return self

    def with_property(self, key: str, value: Any) -> ActivityLogger:
        self._properties[key] = value
        return self

    def event(self, event: str) -> ActivityLogger:
        self._event = event
        return self

    def _resolve_causer(self) -> Any:
        if self._causer is not None:
            return self._causer
        from arvel.support import current_user

        return current_user.get()

    async def log(self, description: str) -> Activity:
        """Persist and return the:class:`Activity`."""
        subject_type, subject_id = _identify(self._subject)
        causer_type, causer_id = _identify(self._resolve_causer())
        return await Activity.create(
            log_name=self._log_name,
            description=description,
            subject_type=subject_type,
            subject_id=subject_id,
            causer_type=causer_type,
            causer_id=causer_id,
            event=self._event,
            properties=self._properties,
        )


def activity(log_name: str = "default") -> ActivityLogger:
    """Start a fluent activity log entry (Spatie ``activity()``)."""
    return ActivityLogger(log_name)


class LogsActivity(ModelHost):
    """Mixin: auto-log a model's create/update/delete to the activity log (the audit trail).

    Mix in **before** ``Model`` so the lifecycle hooks run (Python MRO). Configure via class
    attributes: ``__log_name__``, ``__logs_events__``, ``__log_attributes__`` (``["*"]`` = all),
    and ``__log_only_dirty__`` (updates record only changed attributes; skips an empty update).
    """

    __log_name__: ClassVar[str] = "default"
    __logs_events__: ClassVar[tuple[str, ...]] = ("created", "updated", "deleted")
    __log_attributes__: ClassVar[list[str]] = ["*"]
    __log_only_dirty__: ClassVar[bool] = True
    # (created?, changed-new, old) captured during `saving` (originals are reset before `saved`).
    _activity_snapshot: tuple[bool, dict[str, Any], dict[str, Any]] = (False, {}, {})

    def _activity_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = dict(self._attributes)
        if self.__log_attributes__ == ["*"]:
            return attrs
        return {k: attrs[k] for k in self.__log_attributes__ if k in attrs}

    async def _record_activity(self, event: str, properties: dict[str, Any]) -> None:
        await (
            activity(self.__log_name__)
            .performed_on(self)
            .event(event)
            .with_properties(properties)
            .log(event)
        )

    async def _fire(self, hook: str) -> Any:
        if hook == "saving":
            dirty: dict[str, Any] = self.get_dirty()
            originals: dict[str, Any] = {k: self.get_original(k) for k in dirty}
            self._activity_snapshot = (not self._exists, dirty, originals)
        result: Any = await super()._fire(hook)
        if hook == "saved":
            created, dirty, old = self._activity_snapshot
            event = "created" if created else "updated"
            if event in self.__logs_events__:
                if created:
                    await self._record_activity(event, {"attributes": self._activity_attributes()})
                elif dirty or not self.__log_only_dirty__:
                    new = dirty if self.__log_only_dirty__ else self._activity_attributes()
                    await self._record_activity(event, {"old": old, "attributes": new})
        elif hook == "deleted" and "deleted" in self.__logs_events__:
            await self._record_activity("deleted", {"old": self._activity_attributes()})
        return result


__all__ = ["Activity", "ActivityLogger", "LogsActivity", "activity"]
