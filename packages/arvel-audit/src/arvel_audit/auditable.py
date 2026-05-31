"""``Auditable`` mixin — record create/update/delete to ``audit_entries`` automatically.

Add ``Auditable`` to a model and every persisted change writes an ``AuditEntry``
inside the same transaction as the change itself. Columns named in
``__audit_redact__`` are masked before the row is written, so secrets never
land in the trail even transiently.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from arvel.context.facade import Context
from arvel.database.session import get_active_session

from arvel_audit._identity import model_key, morph_type
from arvel_audit.config import AuditConfig
from arvel_audit.models import AuditEntry

if TYPE_CHECKING:
    from arvel.database.model import Model

REDACTED = "***"

# Models that mix in Auditable, tracked so the provider can re-assert wiring.
_AUDITABLE_MODELS: set[type[Auditable]] = set()


def _audit_enabled() -> bool:
    return AuditConfig().enabled


class Auditable:
    """Mixin that records this model's lifecycle changes to the audit trail."""

    # Column names masked as "***" in both old and new values.
    __audit_redact__: ClassVar[frozenset[str] | set[str] | tuple[str, ...]] = ()
    # Column names left out of the trail entirely (e.g. volatile timestamps).
    __audit_exclude__: ClassVar[frozenset[str] | set[str] | tuple[str, ...]] = ()
    # Set once observers are wired so re-running boot() never double-records.
    _audit_wired: ClassVar[bool] = False

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        _AUDITABLE_MODELS.add(cls)
        cls.install_audit_observers()

    @classmethod
    def audit_redacted_fields(cls) -> frozenset[str]:
        return frozenset(str(f) for f in cls.__audit_redact__)

    @classmethod
    def audit_excluded_fields(cls) -> frozenset[str]:
        return frozenset(str(f) for f in cls.__audit_exclude__)

    @classmethod
    def install_audit_observers(cls) -> None:
        """Attach the lifecycle callbacks once. Idempotent across repeated boots."""
        if cls._audit_wired:
            return
        on = getattr(cls, "on", None)
        if on is None:
            return
        on("updating", _capture_update)
        on("created", _record_created)
        on("updated", _record_updated)
        on("deleting", _capture_delete)
        on("deleted", _record_deleted)
        cls._audit_wired = True


def wire_all_auditable() -> None:
    """Re-assert observer wiring for every Auditable model (called from boot())."""
    for model in _AUDITABLE_MODELS:
        model.install_audit_observers()


def _redact(cls: type[Auditable], values: dict[str, Any]) -> dict[str, Any]:
    redacted = cls.audit_redacted_fields()
    excluded = cls.audit_excluded_fields()
    out: dict[str, Any] = {}
    for key, value in values.items():
        if key in excluded:
            continue
        out[key] = REDACTED if key in redacted else value
    return out


def _actor_id() -> str | None:
    actor = Context.get("user_id", None)
    return None if actor is None else str(actor)


async def _persist(
    instance: Model,
    *,
    action: str,
    old_values: dict[str, Any],
    new_values: dict[str, Any],
) -> None:
    session = get_active_session()
    entry = AuditEntry(
        action=action,
        model_type=morph_type(instance),
        model_id=model_key(instance),
        old_values=old_values,
        new_values=new_values,
        actor_id=_actor_id(),
    )
    session.add(entry)
    await session.flush()


async def _record_created(instance: Auditable) -> None:
    if not _audit_enabled():
        return
    model: Model = instance  # type: ignore[assignment]
    new_values = _redact(type(instance), model.to_dict())
    await _persist(model, action="created", old_values={}, new_values=new_values)


async def _capture_update(instance: Auditable) -> None:
    model: Model = instance  # type: ignore[assignment]
    dirty = model.get_dirty()
    old = {key: model.get_original(key) for key in dirty}
    # Stash before flush clears the history; consumed by _record_updated.
    object.__setattr__(instance, "_audit_pending_update", (old, dict(dirty)))


async def _record_updated(instance: Auditable) -> None:
    pending: tuple[dict[str, Any], dict[str, Any]] | None = getattr(
        instance, "_audit_pending_update", None
    )
    if pending is not None:
        object.__setattr__(instance, "_audit_pending_update", None)
    if not _audit_enabled() or pending is None:
        return
    old, new = pending
    if not new:
        return
    cls = type(instance)
    model: Model = instance  # type: ignore[assignment]
    await _persist(
        model, action="updated", old_values=_redact(cls, old), new_values=_redact(cls, new)
    )


async def _capture_delete(instance: Auditable) -> None:
    model: Model = instance  # type: ignore[assignment]
    object.__setattr__(instance, "_audit_pending_delete", model.to_dict())


async def _record_deleted(instance: Auditable) -> None:
    snapshot: dict[str, Any] | None = getattr(instance, "_audit_pending_delete", None)
    if snapshot is not None:
        object.__setattr__(instance, "_audit_pending_delete", None)
    if not _audit_enabled():
        return
    model: Model = instance  # type: ignore[assignment]
    old = _redact(type(instance), snapshot if snapshot is not None else model.to_dict())
    await _persist(model, action="deleted", old_values=old, new_values={})


__all__ = ["REDACTED", "Auditable", "wire_all_auditable"]
