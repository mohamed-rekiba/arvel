"""arvel.queue.serialization — the job payload codec: class+args/kwargs or instance state ->
JSON, and back. A pure leaf module (DR-0048/E14 V6): every function here closes over nothing but
its own arguments, so it needs no manager/worker collaborator — only ``Job`` in (stringized) type
annotations. Kept lazy on ``msgspec``/``arvel.database``/``arvel.telemetry`` so ``import
arvel.queue`` stays light (G2).

Model args are serialized as ``(class, pk)`` refs and re-fetched fresh in the worker
(:func:`model_ref`); jobs carry no live objects across the broker (01 §5: no closures/handles).
"""

from __future__ import annotations

import importlib
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from arvel.queue import Job


def _qualified_name(cls: Any) -> str:
    return f"{cls.__module__}:{cls.__qualname__}"


def _load(qualified: str) -> Any:
    module_name, _, qualname = qualified.partition(":")
    return getattr(importlib.import_module(module_name), qualname)


#: Job classes loadable from a broker payload, keyed by ``module:qualname``. Populated by
#: ``Job.__init_subclass__`` at class-definition time — see :func:`register_job`.
_JOB_REGISTRY: dict[str, type] = {}


def register_job(cls: type) -> None:
    """Record ``cls`` as a job class that :func:`deserialize` may instantiate."""
    _JOB_REGISTRY[_qualified_name(cls)] = cls


def _load_job(qualified: str) -> Any:
    """Resolve a job class from the registry — a **lookup, never an import**.

    `deserialize` calls the class it resolves with payload-supplied args, so resolving via
    `importlib.import_module` would let anyone with broker write access import and call an
    arbitrary target (`{"job": "os:system", "args": [...]}`) — RCE on every worker. The
    membership test has to *replace* the import rather than follow it: importing an
    attacker-named module runs its module-level side effects before any `issubclass` check
    could fire.

    A job is registered when its class body executes, so worker processes must import their
    job modules before consuming (arvel's boot does; a lazily-loading deployment must too).
    """
    try:
        return _JOB_REGISTRY[qualified]
    except KeyError:
        raise ValueError(
            f"refusing to load unregistered job class {qualified!r} from a queue payload — "
            "the job's module must be imported by the worker before it can run"
        ) from None


def model_ref(value: Any) -> Any:
    """Make a value JSON-safe for the broker, **recursively**: a Model → a ``(class, pk)`` ref,
    ``bytes`` → a tagged base64 string (msgspec encodes bytes to base64 but can't decode them back to
    ``bytes`` without type info — e.g. a queued mailable's binary attachment), and lists/dicts are
    walked so nested models/bytes are handled too. Tuples become lists (JSON has no tuples).

    Jobs carry no live objects across the broker (01 §5: no closures/handles). A model is reduced to
    its class + primary key on dispatch, then re-fetched fresh in the worker.
    """
    from arvel.database import Model

    if isinstance(value, Model):
        pk = type(value).__primary_key__
        return {"__model__": _qualified_name(type(value)), "__id__": getattr(value, pk)}
    if isinstance(value, bytes):
        import base64

        return {"__bytes__": base64.b64encode(value).decode("ascii")}
    if isinstance(value, datetime):
        # msgspec has no type hint to decode back to `datetime` from a generic `json.decode` (no
        # schema) — tag it, mirroring the `bytes` case, so e.g. a job's `retry_until` round-trips.
        return {"__datetime__": value.isoformat()}
    if isinstance(value, (list, tuple)):
        return [model_ref(item) for item in cast("list[Any]", value)]
    if isinstance(value, dict):
        return {key: model_ref(item) for key, item in cast("dict[Any, Any]", value).items()}
    return value


def _is_model_ref(value: Any) -> bool:
    return isinstance(value, dict) and "__model__" in value


async def _rehydrate(value: Any) -> Any:
    if _is_model_ref(value):
        ref = cast("dict[str, Any]", value)
        model_cls = _load(str(ref["__model__"]))
        return await model_cls.find(ref["__id__"])
    if isinstance(value, dict) and "__bytes__" in value:
        import base64

        return base64.b64decode(str(cast("dict[str, Any]", value)["__bytes__"]))
    if isinstance(value, dict) and "__datetime__" in value:
        return datetime.fromisoformat(str(cast("dict[str, Any]", value)["__datetime__"]))
    if isinstance(value, list):
        return [await _rehydrate(item) for item in cast("list[Any]", value)]
    if isinstance(value, dict):
        return {key: await _rehydrate(item) for key, item in cast("dict[Any, Any]", value).items()}
    return value


def _trace_carrier() -> dict[str, str]:
    """The current W3C trace context as a carrier, to ride along in a job payload so the worker can
    continue the dispatching trace (cross-process linking). Empty + no opentelemetry import when
    tracing is off."""
    from arvel.telemetry import is_tracing_enabled

    if not is_tracing_enabled():
        return {}
    from opentelemetry.propagate import inject

    carrier: dict[str, str] = {}
    inject(carrier)
    return carrier


#: Job attributes that are envelope bookkeeping (trace/Context carry-over), not job state — excluded
#: from `serialize_instance`'s state walk (each is re-applied explicitly on deserialize instead, so a
#: re-serialized-in-flight job — a chain link, a retry-release — doesn't double them into `state`).
_ENVELOPE_ATTRS = ("__arvel_trace__", "__arvel_context__", "__arvel_log_context__")


def _log_context_carrier() -> dict[str, Any]:
    """The ENTIRE bound log context at dispatch time (``request_id`` and whatever else the request
    bound — ``user_id``, ``tenant_id``, …), so the worker re-binds all of it and a queue job's logs
    carry the same context as the request that dispatched it. Values are coerced JSON-safe (non-
    primitives → ``str``) so an exotic bound value can never make the dispatch payload unencodable."""
    import structlog

    safe: dict[str, Any] = {}
    for key, value in structlog.contextvars.get_contextvars().items():
        safe[key] = (
            value if isinstance(value, (str, int, float, bool)) or value is None else str(value)
        )
    return safe


def serialize(job_cls: type, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    import msgspec

    from arvel.support.context import Context

    return msgspec.json.encode(
        {
            "job": _qualified_name(job_cls),
            "args": [model_ref(a) for a in args],
            "kwargs": {k: model_ref(v) for k, v in kwargs.items()},
            "_trace": _trace_carrier(),
            "_context": Context.dehydrate(),
            "_log_context": _log_context_carrier(),
        }
    ).decode()


def _apply_envelope(job: Job, data: dict[str, Any]) -> None:
    """Stamp the trace carrier + dehydrated Context captured at dispatch time onto ``job`` — the
    worker hydrates the Context from this before running `handle()` (see `JobWorker._invoke`)."""
    job.__arvel_trace__ = data.get("_trace")  # parent trace for the job span
    job.__arvel_context__ = data.get("_context")  # SUPPORT-FOUNDATION carry-over
    job.__arvel_log_context__ = data.get(
        "_log_context"
    )  # the request's full bound log context, if any


async def deserialize(payload: str) -> Job:
    import msgspec

    data = msgspec.json.decode(payload)
    job_cls = _load_job(str(data["job"]))
    args = [await _rehydrate(a) for a in data["args"]]
    kwargs = {k: await _rehydrate(v) for k, v in data["kwargs"].items()}
    job: Job = job_cls(*args, **kwargs)
    _apply_envelope(job, data)
    return job


def serialize_instance(job: Job) -> str:
    """Serialize an already-constructed job by its attribute state (Bus dispatches instances).

    Model-valued attributes become ``(class, pk)`` refs, exactly as for arg serialization.
    """
    import msgspec

    from arvel.support.context import Context

    state = {key: model_ref(val) for key, val in vars(job).items() if key not in _ENVELOPE_ATTRS}
    return msgspec.json.encode(
        {
            "job": _qualified_name(type(job)),
            "state": state,
            "_trace": _trace_carrier(),
            "_context": Context.dehydrate(),
            "_log_context": _log_context_carrier(),
        }
    ).decode()


async def deserialize_instance(payload: str) -> Job:
    import msgspec

    data = msgspec.json.decode(payload)
    job_cls = _load_job(str(data["job"]))
    job: Job = job_cls.__new__(job_cls)  # bypass __init__; restore attribute state directly
    for key, val in cast("dict[str, Any]", data["state"]).items():
        setattr(job, key, await _rehydrate(val))
    _apply_envelope(job, data)
    return job


async def deserialize_any(payload: str) -> Job:
    """Deserialize either payload shape — class + args/kwargs (``serialize``, from ``push``) or
    instance state (``serialize_instance``, from ``push_instance``). The broker runner takes both
    rails, so it must dispatch on the payload: instance payloads carry ``state``, the others ``args``."""
    import msgspec

    data = msgspec.json.decode(payload)
    return await (deserialize_instance(payload) if "state" in data else deserialize(payload))


def encode_instance(obj: object) -> dict[str, Any]:
    """JSON-safe ``{class, state}`` view of an arbitrary object (its ``vars()``, model attrs → refs).

    For a *nested* serializable value a job carries across the broker — e.g. a queued ``Mailable``,
    which msgspec can't encode directly. Reconstruct with :func:`decode_instance` in the worker."""
    return {
        "__class__": _qualified_name(type(obj)),
        "__state__": {key: model_ref(val) for key, val in vars(obj).items()},
    }


async def decode_instance(data: dict[str, Any]) -> Any:
    """Rebuild an object encoded by :func:`encode_instance` — bypasses ``__init__`` and restores the
    attribute state (model refs re-fetched fresh), mirroring :func:`deserialize_instance`."""
    cls = _load(str(data["__class__"]))
    obj = cls.__new__(cls)
    for key, val in cast("dict[str, Any]", data["__state__"]).items():
        setattr(obj, key, await _rehydrate(val))
    return obj


__all__ = [
    "decode_instance",
    "deserialize",
    "deserialize_any",
    "deserialize_instance",
    "encode_instance",
    "model_ref",
    "register_job",
    "serialize",
    "serialize_instance",
]
