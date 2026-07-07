"""arvel.queue — jobs + queue on **taskiq** (mandated engine; the ``[queue]`` extra).

``Job`` is the app's base (``await MyJob.dispatch(...)``); ``QueueManager`` wraps a real
taskiq broker selected from the ``queue`` config (``memory`` core / ``redis`` via ``[queue-redis]`` /
``amqp`` via ``[queue-amqp]``), serializing the job to JSON (no closures) and running ``handle()``
(with container DI) in the worker. Model args are
serialized as ``(class, pk)`` refs and re-fetched fresh in the worker (``model_ref``). taskiq
is imported lazily so ``import arvel`` stays light. Bus/scheduler/broadcasting are follow-ons.
Grounded in knowledge/port/12-queues.md.
"""

from __future__ import annotations

import contextlib
import importlib
from collections.abc import Iterable
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from arvel.kernel import Settings
from arvel.support.manager import Manager

if TYPE_CHECKING:
    from arvel.queue.batch import Batch as Batch
    from arvel.queue.batch import JobBatch as JobBatch
    from arvel.queue.failed import FailedJob as FailedJob
    from arvel.queue.jobs import QueuedJob as QueuedJob


class QueueSettings(Settings):
    """Typed, validated view over the ``queue`` config section (DR-0016).

    ``default`` names the broker driver — ``memory`` (core), ``redis`` (the ``[queue-redis]`` extra),
    or ``amqp`` (RabbitMQ/any AMQP broker, the ``[queue-amqp]`` extra). ``url`` is the single DSN for
    the active driver (a ``redis://`` or ``amqp://`` endpoint); ``memory`` ignores it. ``retry_after``
    is the visibility timeout (seconds): a reserved ``jobs`` row older than this is assumed to belong
    to a dead worker and is reclaimed; a job's own
    ``retry_after`` class attribute overrides this default when set.
    """

    __config_key__ = "queue"
    default: str = "memory"
    url: str = "redis://localhost:6379/0"
    retry_after: int = 90


def _qualified_name(cls: Any) -> str:
    return f"{cls.__module__}:{cls.__qualname__}"


def _load(qualified: str) -> Any:
    module_name, _, qualname = qualified.partition(":")
    return getattr(importlib.import_module(module_name), qualname)


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
_ENVELOPE_ATTRS = ("__arvel_trace__", "__arvel_context__")


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
        }
    ).decode()


def _apply_envelope(job: Job, data: dict[str, Any]) -> None:
    """Stamp the trace carrier + dehydrated Context captured at dispatch time onto ``job`` — the
    worker hydrates the Context from this before running `handle()` (see `QueueManager._invoke`)."""
    job.__arvel_trace__ = data.get("_trace")  # parent trace for the job span
    job.__arvel_context__ = data.get("_context")  # SUPPORT-FOUNDATION carry-over


async def deserialize(payload: str) -> Job:
    import msgspec

    data = msgspec.json.decode(payload)
    job_cls = _load(str(data["job"]))
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
        }
    ).decode()


async def deserialize_instance(payload: str) -> Job:
    import msgspec

    data = msgspec.json.decode(payload)
    job_cls = _load(str(data["job"]))
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


class Job:
    """Base job: subclass and implement ``handle()``."""

    queue: str = "default"
    #: Defer enqueue until the surrounding DB transaction commits (dropped on rollback);
    #: immediate when no transaction is open. Per-call form: :meth:`dispatch_after_commit`.
    after_commit: bool = False
    tries: int = 3
    backoff: int | list[int] = 5
    timeout: int = 60
    #: Visibility-timeout override (seconds) for this job's class; ``None`` -> the
    #: ``queue.retry_after`` config default (see `QueueManager._reclaim_stuck_jobs`).
    retry_after: int | None = None
    #: An extra cap on attempts, alongside `tries` (ponytail: a simple shared ceiling, not
    #: the full manual-release-vs-exception distinction — add that nuance if a job needs it).
    max_exceptions: int | None = None
    #: Stop retrying past this moment regardless of `tries` left.
    retry_until: datetime | None = None

    # Queue envelope state, assigned per instance by the dispatcher/worker. Declared here
    # (typed, defaulted) so assignments type-check; the arvel-prefixed names keep them out
    # of app-job attribute space, and instance assignments still travel in the payload
    # (vars()-based serialization is unchanged).
    __arvel_trace__: Any = None
    __arvel_context__: Any = None
    __arvel_attempts__: int = 0
    __arvel_chain__: list[str] | None = None
    __arvel_chain_catch__: str | None = None
    __arvel_batch__: Any = None

    async def handle(self) -> Any:
        raise NotImplementedError(f"{type(self).__name__} must implement handle()")

    async def failed(self, exc: BaseException) -> None:
        """Hook invoked when the job exhausts its retries (override to alert/log)."""

    def middleware(self) -> list[Any]:
        """Job middleware this job runs `handle()` through — e.g.
        ``arvel.queue.middleware.WithoutOverlapping``/``RateLimited``. Empty by default."""
        return []

    @classmethod
    async def dispatch(cls, *args: Any, **kwargs: Any) -> Any:
        from arvel.kernel import app, has_application

        manager = (
            app().make("queue") if has_application() and app().bound("queue") else QueueManager()
        )
        return await manager.push(cls, args, kwargs)

    @classmethod
    async def dispatch_after_commit(cls, *args: Any, **kwargs: Any) -> Any:
        """Like :meth:`dispatch`, but defers the enqueue to the surrounding transaction's
        commit regardless of the class-level ``after_commit`` default. Returns ``None`` when
        deferred (there is no broker task yet)."""
        from arvel.kernel import app, has_application

        manager = (
            app().make("queue") if has_application() and app().bound("queue") else QueueManager()
        )
        return await manager.push(cls, args, kwargs, after_commit=True)

    @classmethod
    async def dispatch_after(cls, delay: float, *args: Any, **kwargs: Any) -> Any:
        """Dispatch this job to run after ``delay`` seconds.
        Durable, DB-backed — see :meth:`QueueManager.dispatch_after`."""
        from arvel.kernel import app, has_application

        manager = (
            app().make("queue") if has_application() and app().bound("queue") else QueueManager()
        )
        job = cls(*args, **kwargs)
        # A unique job acquires its lock at the user dispatch entry (as `push` does for immediate
        # dispatch) so a delayed dispatch can't double-enqueue. Internal re-dispatch through
        # `QueueManager.dispatch_after` (filtered-park, retry-release) stays lock-free, reusing the
        # lock the job already holds — mirroring the `push`/`push_instance` split.
        from arvel.queue.middleware import ShouldBeUnique, unique_lock_for

        if isinstance(job, ShouldBeUnique) and not await unique_lock_for(job).acquire():
            return None  # already queued/running — don't double-enqueue
        return await manager.dispatch_after(delay, job)


@contextlib.contextmanager
def _job_span(job: Job) -> Any:
    """A CONSUMER span around a job's execution when tracing is on; a no-op (and no opentelemetry
    import) otherwise. Runs inline → nests under the dispatching request's span when there is one."""
    from arvel.telemetry import is_tracing_enabled

    if not is_tracing_enabled():
        yield
        return
    from opentelemetry import trace
    from opentelemetry.trace import SpanKind

    name = type(job).__name__
    tracer = trace.get_tracer("arvel.queue")
    # Traceparent captured at dispatch makes this job a child of the dispatching request even in
    # a separate worker process; no carrier -> ambient nesting or a fresh root.
    carrier = getattr(job, "__arvel_trace__", None)
    if carrier:
        from opentelemetry.propagate import extract

        cm = tracer.start_as_current_span(
            f"job {name}", context=extract(carrier), kind=SpanKind.CONSUMER
        )
    else:
        cm = tracer.start_as_current_span(f"job {name}", kind=SpanKind.CONSUMER)
    with cm as span:
        span.set_attribute("messaging.system", "arvel.queue")
        span.set_attribute("messaging.operation", "process")
        span.set_attribute("messaging.destination.name", _resolved_label(job))
        span.set_attribute("code.namespace", type(job).__module__)
        span.set_attribute("code.function", name)
        yield span


def _resolved_label(job: Job) -> str:
    """The queue label a job class resolves to — through the bound manager's registry when an
    app is up (so spans and failure records show the routed queue), else the class attribute."""
    from arvel.kernel import app, has_application

    if has_application() and app().bound("queue"):
        label: str = app().make("queue")._queue_label(type(job), None)
        return label
    return str(getattr(job, "queue", "default"))


def _backoff_for(backoff: int | list[int] | tuple[int, ...], attempt: int) -> float:
    """The delay before ``attempt``'s retry: a flat number, or per-attempt from a list (its last
    entry repeats once the list is exhausted)."""
    if isinstance(backoff, (list, tuple)):
        return backoff[min(attempt - 1, len(backoff) - 1)]
    return backoff


def _retry_should_stop(job: Job, attempt: int, tries: int) -> bool:
    """Whether to give up after this failed ``attempt`` rather than retry again: ``tries``
    exhausted, ``max_exceptions`` capped (ponytail: a simple shared ceiling — see the attribute's
    docstring), or past ``retry_until``."""
    max_exceptions = getattr(job, "max_exceptions", None)
    if max_exceptions is not None and attempt >= max_exceptions:
        return True
    retry_until = getattr(job, "retry_until", None)
    if retry_until is not None:
        from arvel.dates import Date

        if Date.now() >= Date.from_py(retry_until):
            return True
    return attempt >= tries


def _hydrate_context(job: Job) -> None:
    """Restore the Context dehydrated at dispatch time (SUPPORT-FOUNDATION carry-over) before
    running the job — scoped to this job's own asyncio task (contextvars), never leaking to a
    sibling job running concurrently."""
    payload = getattr(job, "__arvel_context__", None)
    if payload:
        from arvel.support.context import Context

        Context.hydrate(payload)


def _wrap_with_middleware(job: Job, base_call: Any) -> Any:
    """Wrap ``base_call`` (the plain ``handle()`` invocation) so it runs through ``job.middleware()``
    (queue/middleware.py's ``WithoutOverlapping``/``RateLimited``/``ThrottlesExceptions``, or a
    user's own) via the existing onion `Pipeline` — no job-specific pipeline machinery, this is
    the same `(value, next)` shape HTTP middleware already uses."""
    middleware = job.middleware() if hasattr(job, "middleware") else []
    if not middleware:
        return base_call

    async def _run() -> Any:
        from arvel.support.pipeline import Pipeline

        return await Pipeline().send(job).through(middleware).then(lambda _job: base_call())

    return _run


async def run_job_with_retries(
    job: Job,
    *,
    runner: Any = None,
    sleep: Any = None,
    release: Any = None,
    on_success: Any = None,
    on_exhausted: Any = None,
) -> Any:
    """Run a job, retrying on failure up to ``job.tries`` (honoring ``max_exceptions``/
    ``retry_until``) with ``job.backoff`` between attempts; invoke ``job.failed(exc)`` + record a
    ``FailedJob`` once retries are exhausted. Hydrates the dispatch-time ``Context`` first. Each
    attempt is bounded by ``job.timeout`` (a timeout counts as a failed attempt — cooperative
    cancel via ``asyncio.wait_for``). This is the worker's per-job execution policy.

    ``runner`` overrides how ``handle`` is called (e.g. with DI). Two retry strategies:

    - ``release`` given (a durable queue — DB/redis/amqp): try **once** this pass; on a non-final
      failure, ``await release(job, delay, attempt)`` releases the job back to the queue store
      instead of blocking this worker with an inline sleep. The next attempt happens on a later
      worker pass (``release_due_jobs`` redispatches it), resuming from ``job.__arvel_attempts__``.
    - ``release`` omitted (the in-memory/sync driver, or a direct/test call): the classic inline
      loop — ``sleep`` (injectable) between attempts, all within this one call.

    ``on_success``/``on_exhausted`` are ``QueueManager``'s chain-continuation hooks (dispatch the
    next chained job / run the chain's ``catch``); optional, so direct callers (tests) are
    unaffected.
    """
    import asyncio

    _hydrate_context(job)
    invoke = runner if runner is not None else job.handle
    timeout = getattr(job, "timeout", None)
    tries = max(1, int(getattr(job, "tries", 1)))

    async def _call() -> Any:
        return await asyncio.wait_for(invoke(), timeout=timeout) if timeout else await invoke()

    async def _give_up(exc: BaseException) -> None:
        await job.failed(exc)
        await _record_failed_job(job, exc)
        if on_exhausted is not None:
            await on_exhausted(exc)

    async def _succeed(result: Any) -> Any:
        if on_success is not None:
            await on_success(result)
        return result

    if release is not None:
        attempt = int(getattr(job, "__arvel_attempts__", 0)) + 1
        try:
            result = await _call()
        except Exception as exc:
            if _retry_should_stop(job, attempt, tries):
                await _give_up(exc)
                return None
            await release(job, _backoff_for(job.backoff, attempt), attempt)
            return None
        return await _succeed(result)

    wait = sleep if sleep is not None else asyncio.sleep
    for attempt in range(1, tries + 1):
        try:
            result = await _call()
        except Exception as exc:
            if _retry_should_stop(job, attempt, tries):
                await _give_up(exc)
                return None
            await wait(_backoff_for(job.backoff, attempt))
        else:
            return await _succeed(result)
    return None


async def _record_failed_job(job: Job, exc: BaseException) -> None:
    """Persist a ``failed_jobs`` row for a job that exhausted its retries. No-op when
    no DB is bound — the ``failed()`` hook already ran, so nothing is lost and nothing crashes."""
    from arvel.kernel import app, has_application

    if not (has_application() and app().bound("db")):
        return
    from arvel.dates import Date
    from arvel.queue.failed import FailedJob

    await FailedJob.create(
        queue=_resolved_label(job),
        payload=serialize_instance(job),
        exception=f"{type(exc).__name__}: {exc}",
        failed_at=Date.now(),
    )


class _WorkerOptions:
    """Bookkeeping for one active ``work()`` run — worker-flag state (max-jobs/rest/idle
    detection). ``None`` on the manager outside an active ``work()`` call, so dispatch paths that
    reuse ``_invoke`` (e.g. release-due, a same-process ``dispatch``) are unaffected."""

    __slots__ = (
        "last_tick_processed",
        "max_jobs",
        "processed",
        "queues",
        "rest",
        "stop_when_empty",
    )

    def __init__(
        self,
        *,
        max_jobs: int | None,
        rest: float,
        stop_when_empty: bool,
        queues: list[str] | None = None,
    ) -> None:
        self.max_jobs = max_jobs
        self.rest = rest
        self.stop_when_empty = stop_when_empty
        #: `work(queues=[...])` — the named queues this run consumes, in priority order
        #: (`None` = every queue). See `QueueManager._invoke`/`release_due_jobs`.
        self.queues = queues
        self.processed = 0
        self.last_tick_processed = 0


async def _stop_after(stop: Any, seconds: float) -> None:
    """``--max-time``: request a stop once ``seconds`` have elapsed."""
    import asyncio

    await asyncio.sleep(seconds)
    stop.set()


async def _stop_on_memory(stop: Any, limit_mb: float, interval: float) -> None:
    """``--memory``: request a stop once this process's RSS exceeds ``limit_mb`` (a supervisor
    restarts the worker fresh — the memory-leak safety valve)."""
    import asyncio
    import resource
    import sys

    # ru_maxrss: KiB on Linux, bytes on macOS — a well-known stdlib quirk (no portable API).
    unit = 1024 * 1024 if sys.platform == "darwin" else 1024
    while True:
        await asyncio.sleep(interval)
        rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / unit
        if rss_mb >= limit_mb:
            stop.set()
            return


class QueueManager(Manager):
    """Pushes jobs onto a config-selected taskiq broker (the Manager 'driver': ``memory``/``redis``/
    ``amqp``) and runs them via a single wrapper task."""

    def __init__(self, app: Any = None, broker: Any = None) -> None:
        super().__init__(app)
        self._broker = broker  # an explicit broker passed in wins over the config-selected one
        self._routes: dict[type, str] = {}  # central per-class queue routing (last write wins)
        self._task: Any = None
        self._started = False
        self._worker_options: _WorkerOptions | None = None  # set only while work() is running
        self._worker_stop: Any = None  # the active work() run's stop/finish event

    def route(self, job_cls: type, *, queue: str) -> None:
        """Route ``job_cls`` to ``queue`` by default — declared once (a provider), not on the
        class. Precedence: an explicit ``queue=`` at dispatch > a ``queue`` attribute declared
        on the class itself > this registry > ``"default"``. Re-registering replaces."""
        self._routes[job_cls] = queue

    def _queue_label(self, job_cls: type, explicit: str | None) -> str:
        if explicit:
            return explicit
        for klass in job_cls.__mro__:
            if klass is Job:
                break  # Job.queue = "default" is the fallback, not a declaration
            declared = klass.__dict__.get("queue")
            if isinstance(declared, str):
                return declared
        routed = self._routes.get(job_cls)
        if routed is not None:
            return routed
        return "default"

    def default_driver(self) -> str:
        driver: str = self._settings(QueueSettings).default
        if driver not in ("memory", "redis", "amqp"):
            raise ValueError(f"Unknown queue driver {driver!r} (expected: memory, redis, amqp)")
        return driver

    def create_memory_driver(self) -> Any:
        from taskiq import InMemoryBroker

        return InMemoryBroker()

    def create_redis_driver(self) -> Any:
        try:
            from taskiq_redis import ListQueueBroker
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise ImportError(
                "the 'redis' queue driver needs the [queue-redis] extra (taskiq-redis)"
            ) from exc
        return ListQueueBroker(self._settings(QueueSettings).url)

    def create_amqp_driver(self) -> Any:
        try:
            from taskiq_aio_pika import AioPikaBroker
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise ImportError(
                "the 'amqp' queue driver needs the [queue-amqp] extra (taskiq-aio-pika)"
            ) from exc
        return AioPikaBroker(self._settings(QueueSettings).url)

    @property
    def broker(self) -> Any:
        return self._broker if self._broker is not None else self.driver()

    def _is_durable(self) -> bool:
        """Whether a failed attempt should be released back to the ``jobs`` table rather than
        retried inline. The release mechanism is DB-table-based regardless of which broker carries
        messages (B1/spec: DB/redis/amqp release-back), so the only real requirement is a bound
        DB. Without one there's nowhere to persist the release — the in-memory/sync driver
        typically has no DB either, so it naturally takes the documented inline-retry fallback."""
        from arvel.kernel import app, has_application

        return has_application() and app().bound("db")

    async def _release_for_retry(self, job: Job, delay: float, attempt: int) -> None:
        """B1: release a failed job back to the queue store with ``available_at = now + delay``
        instead of an inline ``asyncio.sleep`` — this worker keeps draining other jobs meanwhile.
        ``attempt`` rides along on the job instance so the next pass (via ``release_due_jobs``)
        resumes counting from where this one left off."""
        job.__arvel_attempts__ = attempt
        # queue=None → dispatch_after resolves through _queue_label, so a route()d class
        # retries on its routed queue, not "default"
        await self.dispatch_after(delay, job, attempts=attempt)

    async def _dispatch_next_link(self, job: Job) -> None:
        """A1: on success, dispatch the next link of ``job``'s chain (if any) — the remaining
        chain travels serialized on the job itself (``__arvel_chain__``, set by
        ``PendingChain.dispatch``/carried forward here), so each link only runs after the prior
        one succeeds."""
        chain: list[str] | None = getattr(job, "__arvel_chain__", None)
        if not chain:
            return
        payload, *rest = chain
        next_job = await deserialize_instance(payload)
        next_job.__arvel_chain__ = rest
        next_job.__arvel_chain_catch__ = job.__arvel_chain_catch__
        await self.push_instance(next_job)

    async def _run_chain_catch(self, job: Job, exc: BaseException) -> None:
        """A1: a chain's ``catch`` (if set) fires once a link exhausts its retries, and the rest
        of the chain never runs. ``catch`` must be a module-level callable (its qualified name is
        what actually travels in the payload — a closure/lambda can't survive serialization)."""
        catch_ref = getattr(job, "__arvel_chain_catch__", None)
        if not catch_ref:
            return
        import inspect

        outcome = _load(catch_ref)(exc)
        if inspect.isawaitable(outcome):
            await outcome

    def _note_job_processed(self) -> float:
        """Worker-flag bookkeeping for the just-finished job: bumps the processed count (checking
        ``--max-jobs``) and returns the configured ``--rest`` seconds to pause before the next one
        (``0`` outside an active ``work()`` run)."""
        options = self._worker_options
        if options is None:
            return 0.0
        options.processed += 1
        if options.max_jobs is not None and options.processed >= options.max_jobs:
            self._worker_stop.set()
        return options.rest

    async def _invoke(self, job: Job, *, queue_label: str | None = None) -> Any:
        import asyncio

        from arvel.queue.middleware import JobShouldBeReleased, ShouldBeUnique, unique_lock_for

        options = self._worker_options
        if options is not None and options.queues is not None:
            # the *actual* routed queue (from the broker message's own labels, passed by
            # `_runner`'s task) when known — a per-dispatch `queue=` override (e.g.
            # `dispatch_after(..., queue=...)`) isn't visible on `type(job)` alone, only on the
            # message that carried it; falls back to the class-based resolution for a direct
            # `_invoke` call with no message context (e.g. a test, or `_release_for_retry`'s
            # inline retry path).
            label = queue_label if queue_label is not None else self._queue_label(type(job), None)
            if label not in options.queues:
                # this worker's `work(queues=[...])` doesn't consume `label` — the receive-time
                # net for brokers without network-level filtering. The broker acks this delivery
                # regardless, so it must not be lost.
                from arvel.kernel import app, has_application

                if has_application() and app().bound("db"):
                    # durable park (jobs table, due now) — another worker's release_due_jobs
                    # re-dispatches it on its own queue.
                    await self.dispatch_after(0, job, queue=label)
                    return None
                # No DB to park into and no other consumer: an inline broker is the sole executor,
                # so running the job here is the only way an already-acked delivery isn't silently
                # lost (DR-0036). Fall through to execute it.

        batch_id = getattr(job, "__arvel_batch__", None)
        if batch_id is not None:
            from arvel.queue.batch import apply_job_outcome, is_batch_cancelled

            if await is_batch_cancelled(batch_id):
                # A prior sibling's failure already cancelled the batch — this job never runs,
                # but still counts toward `pending_jobs` so the batch converges to `finished()`.
                await apply_job_outcome(batch_id, None)
                return None

        async def _release_unique() -> None:
            if isinstance(job, ShouldBeUnique):
                await unique_lock_for(job).force_release()

        async def _on_success(_result: Any) -> None:
            await self._dispatch_next_link(job)
            if batch_id is not None:
                from arvel.queue.batch import apply_job_outcome

                await apply_job_outcome(batch_id, None)
            await _release_unique()

        async def _on_exhausted(exc: BaseException) -> None:
            await self._run_chain_catch(job, exc)
            if batch_id is not None:
                from arvel.queue.batch import apply_job_outcome

                await apply_job_outcome(batch_id, exc)
            await _release_unique()

        runner: Any = None
        if self.app is not None and hasattr(self.app, "call"):
            runner = lambda: self.app.call(job.handle)  # noqa: E731
        runner = _wrap_with_middleware(job, runner or job.handle)

        try:
            with _job_span(job):
                result = await run_job_with_retries(
                    job,
                    runner=runner,
                    release=self._release_for_retry if self._is_durable() else None,
                    on_success=_on_success,
                    on_exhausted=_on_exhausted,
                )
        except JobShouldBeReleased as released:
            # A job middleware (WithoutOverlapping/RateLimited/ThrottlesExceptions) asked for this
            # job back on the queue instead of running — not a failed attempt, so it never touches
            # `tries`/`backoff`, and (unlike `_on_success`/`_on_exhausted`) a unique lock stays held.
            await self._release_job(job, released.delay)
            result = None
        rest = self._note_job_processed()
        if rest:
            await asyncio.sleep(rest)
        return result

    async def _release_job(self, job: Job, delay: float) -> None:
        """Put ``job`` back onto the queue after ``delay`` seconds (a job middleware's
        :class:`~arvel.queue.middleware.JobShouldBeReleased`) — durable (the `jobs` table) when a
        DB is bound, mirroring B1's retry-release; otherwise an inline sleep-then-repush."""
        if self._is_durable():
            await self.dispatch_after(delay, job)  # queue resolved by _queue_label inside
            return
        import asyncio

        if delay:
            await asyncio.sleep(delay)
        await self.push_instance(job)

    def _runner(self) -> Any:
        if self._task is None:
            from taskiq import Context, TaskiqDepends

            manager = self
            # `dependency=Context` explicitly (rather than an annotation taskiq would have to
            # resolve) — this module's own `from __future__ import annotations` turns the
            # parameter annotation into a string, and `Context` is only ever imported lazily
            # here, never at module scope, so taskiq couldn't look it up by name. Built once,
            # outside the `def` (not a call in the default itself), so ruff's B008 doesn't flag it.
            context_dependency = TaskiqDepends(Context)

            @self.broker.task  # type: ignore[untyped-decorator]  # broker is Any (lazy taskiq)
            async def _run_job(payload: str, context: Any = context_dependency) -> Any:
                # `context.message.labels["queue"]` is the *actual* queue this message was routed
                # to (set by `.with_labels(queue=label)` at push time) — `work(queues=[...])`'s
                # filter (`_invoke`) needs this, not a class-level re-derivation, since a
                # per-dispatch `queue=` override only ever lives on the message, never on the job.
                label = context.message.labels.get("queue")
                return await manager._invoke(await deserialize_any(payload), queue_label=label)

            self._task = _run_job
        return self._task

    async def push(
        self,
        job_cls: type,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        *,
        queue: str | None = None,
        after_commit: bool | None = None,
    ) -> Any:
        from arvel.queue.middleware import ShouldBeUnique, unique_lock_for

        wants_deferral = (
            after_commit if after_commit is not None else getattr(job_cls, "after_commit", False)
        )
        if wants_deferral and await self._defer_to_commit(job_cls, args, kwargs, queue=queue):
            return None  # no broker task yet — the enqueue happens at commit

        if issubclass(job_cls, ShouldBeUnique):
            # Only the original `Job.dispatch()` entry point is gated — chain/batch continuation
            # and retry/release redispatch all go through `push_instance` directly, reusing the
            # same in-flight job, so gating there too would lock a job out against itself.
            instance = job_cls(*args, **kwargs)
            if not await unique_lock_for(instance).acquire():
                return None  # already queued/running — silently dropped
        task = self._runner()
        if not self._started:
            await self.broker.startup()
            self._started = True
        # pyright's `issubclass(job_cls, ShouldBeUnique)` narrowing above leaves `job_cls` typed as
        # a union including `type[Unknown]` for the rest of the function (a known narrowing quirk
        # on a bare `type` parameter) — both calls below are exactly as they were before that check.
        label = self._queue_label(job_cls, queue)  # pyright: ignore[reportUnknownArgumentType]
        return (
            await task.kicker()
            .with_labels(queue=label)
            .kiq(
                serialize(job_cls, args, kwargs)  # pyright: ignore[reportUnknownArgumentType]
            )
        )

    async def _defer_to_commit(
        self,
        job_cls: type,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        *,
        queue: str | None,
    ) -> bool:
        """Buffer the enqueue on the event dispatcher's after-commit seam when a transaction
        is open. Returns False (caller enqueues immediately) outside a transaction or when no
        dispatcher is bound — after-commit is a deferral request, not a hard requirement."""
        from arvel.kernel import app, has_application

        if not (has_application() and app().bound("events")):
            return False
        events = app().make("events")
        if not events.in_transaction():
            return False

        async def _enqueue() -> Any:
            # replayed after COMMIT, outside the buffer — after_commit=False so it can't re-defer
            return await self.push(job_cls, args, kwargs, queue=queue, after_commit=False)

        await events.after_commit(_enqueue)  # buffer is open (checked just above, no await between)
        return True

    async def failed_jobs(self) -> list[Any]:
        """The failed-job records, newest first."""
        from arvel.queue.failed import FailedJob

        return list(await FailedJob.order_by("failed_at", "desc").get())

    async def retry_failed(self, failed_id: str | None = None) -> list[Any]:
        """Re-dispatch failed jobs — one by id, or every one. Returns
        the records that were retried (each is re-pushed and its record deleted)."""
        from arvel.queue.failed import FailedJob

        if failed_id is None:
            jobs = list(await FailedJob.get())
        else:
            found = await FailedJob.find(failed_id)
            jobs = [found] if found is not None else []
        for job in jobs:
            await job.retry()
        return jobs

    async def work(
        self,
        queues: list[str] | None = None,
        *,
        release_interval: float = 1.0,
        max_jobs: int | None = None,
        max_time: float | None = None,
        stop_when_empty: bool = False,
        rest: float = 0.0,
        memory: float | None = None,
    ) -> None:
        """Run an in-process worker: consume + execute jobs from the broker until stopped.

        Backs ``arvel queue:work``. For production scale, run taskiq's own worker process
        against the broker; this is the convenient in-process equivalent.

        ``queues`` restricts this run to those named queues, consumed in the given priority
        order — a due row in the durable ``jobs`` table (delayed dispatch, B1 retry-release) is
        released queue-by-queue in that order (all of ``queues[0]``'s due rows before any of
        ``queues[1]``'s); a queue not named is left completely alone (another worker may be
        listening to it). Any job that still reaches this worker for a queue it isn't consuming
        (in-process/direct dispatch, or a broker whose network-level routing can't filter by
        queue — e.g. the ``memory`` broker, which runs a job inline at dispatch time rather than
        through a receive loop) is dropped without running (``_invoke``'s own check) — a clean
        empty poll, never a crash. **Broker-native queue routing** (e.g. AMQP's per-queue
        consumers) isn't wired up in this pass — the ``jobs``-table release order above is what
        actually delivers "priority order" today, for every driver alike; ``None`` (the default)
        consumes every queue, as before.

        Worker flags: ``max_jobs`` stops after N jobs processed;
        ``max_time`` stops after S seconds; ``stop_when_empty`` stops once idle (no job has run and
        nothing was due across a release tick, checked after at least one job has run);
        ``rest`` pauses between jobs; ``memory`` stops once this process's RSS exceeds the given MB
        (for a supervisor to restart it fresh). SIGTERM/SIGINT request the same cooperative stop —
        the in-flight job finishes before the worker exits (taskiq's ``Receiver.listen`` drains
        outstanding tasks once its stop event is set, rather than cancelling them).
        """
        import asyncio
        import contextlib
        import signal

        from taskiq import InMemoryBroker

        self._runner()  # register the wrapper task on the broker
        # A same-process dispatch may have started the broker in client mode; taskiq-aio-pika's
        # startup() isn't idempotent, so shut it down first and restart cleanly in worker mode.
        if self._started:
            await self.broker.shutdown()
            self._started = False
        # Must be set before startup: a consuming broker (e.g. taskiq-aio-pika) only declares its
        # read connection/consumer when is_worker_process is set, else listen() raises.
        self.broker.is_worker_process = True
        await self.broker.startup()
        self._started = True

        finish = asyncio.Event()  # the single stop signal: flags, signals, and taskiq's Receiver
        self._worker_options = _WorkerOptions(
            max_jobs=max_jobs, rest=rest, stop_when_empty=stop_when_empty, queues=queues
        )
        self._worker_stop = finish

        loop = asyncio.get_running_loop()
        handled_signals: list[signal.Signals] = []
        for sig_num in (signal.SIGTERM, signal.SIGINT):
            with contextlib.suppress(NotImplementedError, RuntimeError):
                loop.add_signal_handler(sig_num, finish.set)
                handled_signals.append(sig_num)

        watchers = (
            [asyncio.create_task(_stop_after(finish, max_time))] if max_time is not None else []
        )
        if memory is not None:
            watchers.append(asyncio.create_task(_stop_on_memory(finish, memory, release_interval)))

        releaser = asyncio.create_task(self._release_loop(release_interval, finish))
        try:
            if isinstance(self.broker, InMemoryBroker):
                # runs jobs inline on dispatch and can't be listened to; just wait for a stop condition.
                await finish.wait()
            else:
                from taskiq.receiver import Receiver

                await Receiver(self.broker).listen(finish)  # cooperative: drains in-flight work
        finally:
            # `finish.set()` covers exiting via an external `task.cancel()` too (not just a worker
            # flag) — either way, `_release_loop` then notices cooperatively (never mid-DB-call,
            # which a raw `.cancel()` could interrupt and wedge the connection) and returns on its
            # own, almost always within one tick. The timeout is a last-resort fallback for a truly
            # stuck DB call — same as an unconditional `.cancel()` would risk, just the rare case
            # now instead of the common one.
            finish.set()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(releaser, timeout=release_interval + 1.0)
            for watcher in watchers:
                watcher.cancel()
            for sig_num in handled_signals:
                with contextlib.suppress(NotImplementedError, RuntimeError):
                    loop.remove_signal_handler(sig_num)
            self._worker_options = None
            self._worker_stop = None

    def _on_release_tick(self, released: int) -> None:
        """``--stop-when-empty`` bookkeeping: a tick is idle when nothing was released *and* no
        job has finished since the previous tick. Requires at least one processed job first, so a
        freshly-started worker with nothing dispatched yet doesn't stop before any work arrives."""
        options = self._worker_options
        if options is None or not options.stop_when_empty:
            return
        idle = released == 0 and options.processed == options.last_tick_processed
        options.last_tick_processed = options.processed
        if idle and options.processed > 0:
            self._worker_stop.set()

    async def _release_loop(self, interval: float, stop: Any) -> None:
        """Periodically reclaim stuck reservations + push due delayed jobs onto the broker. A
        transient error never kills the worker.

        Checks ``stop`` (the ``work()`` run's stop event) cooperatively **before** each DB call —
        never mid-call — and returns on its own once set, so ``work()``'s cleanup never has to
        cancel this task while it's mid-flight in a DB operation (which can otherwise wedge an
        async DB connection: cancelling a coroutine bridged onto a sync driver — e.g. aiosqlite's
        greenlet trampoline — mid-operation can leave it unable to close cleanly)."""
        import asyncio
        import contextlib

        from arvel.kernel import app, has_application

        while not stop.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=interval)
            if stop.is_set():
                return
            released = 0
            if has_application() and app().bound("db"):
                try:
                    queues = self._worker_options.queues if self._worker_options else None
                    released = await self.release_due_jobs(queues=queues)
                except Exception:
                    # a transient DB hiccup must not kill the worker — but a permanently
                    # broken DB silently stalling delayed/retry jobs must be visible
                    from arvel.kernel.logging import LogManager

                    LogManager().channel("queue").warning("release_due_jobs_failed", exc_info=True)
            self._on_release_tick(released)

    async def push_instance(self, job: Job, *, queue: str | None = None) -> Any:
        task = self._runner()
        if not self._started:
            await self.broker.startup()
            self._started = True
        label = self._queue_label(type(job), queue)
        return await task.kicker().with_labels(queue=label).kiq(serialize_instance(job))

    async def dispatch_after(
        self, delay: float, job: Job, *, queue: str | None = None, attempts: int = 0
    ) -> Any:
        """Delay a job: persist it to the ``jobs`` table with
        ``available_at = now + delay`` instead of enqueuing now. A worker/scheduler calls
        :meth:`release_due_jobs` to push the due ones. Durable (survives restart); needs a DB.
        ``attempts`` records how many times the job has already run — B1's retry-release reuses
        this same mechanism, so a released-for-retry row shows its real attempt count."""
        import time

        from arvel.kernel import app, has_application

        if not (has_application() and app().bound("db")):
            raise RuntimeError(
                "delayed dispatch needs a configured database (the jobs table); "
                "dispatch without a delay to enqueue immediately"
            )
        from arvel.queue.jobs import QueuedJob

        now = int(time.time())
        return await QueuedJob.create(
            queue=self._queue_label(type(job), queue),
            payload=serialize_instance(job),
            attempts=attempts,
            available_at=now + int(delay),
            created_at=now,
        )

    async def _reclaim_stuck_jobs(self, moment: int) -> None:
        """Visibility timeout: a row whose ``reserved_at`` predates its ``retry_after`` window
        means the worker that claimed it died before finishing (a crash between the atomic claim
        and the delete in :meth:`release_due_jobs`) — free it (clear ``reserved_at``) so another
        worker can pick it up. ``retry_after`` is the job's own class attribute if set, else the
        ``queue.retry_after`` config default."""
        from arvel.queue.jobs import QueuedJob

        default_retry_after = self._settings(QueueSettings).retry_after
        stuck = await QueuedJob.where_not_null("reserved_at").get()
        for row in stuck:
            reserved_at = row.reserved_at
            if reserved_at is None:
                continue
            retry_after = default_retry_after
            with contextlib.suppress(
                Exception
            ):  # an undeserializable row falls back to the default
                job = await deserialize_instance(row.payload)
                override = getattr(job, "retry_after", None)
                if override is not None:
                    retry_after = override
            if moment - int(reserved_at) >= retry_after:
                await (
                    QueuedJob.where("id", "=", row.id)
                    .where("reserved_at", "=", reserved_at)
                    .update({"reserved_at": None})
                )

    async def release_due_jobs(
        self, now: int | None = None, *, queues: list[str] | None = None
    ) -> int:
        """Reclaim any visibility-timed-out reservations, then push every stored job whose
        ``available_at`` has passed onto the broker and delete its row. Returns how many were
        released. A worker (``queue:work``) / scheduler calls this periodically.

        ``queues`` (from an active ``work(queues=[...])`` run) restricts + orders release to
        those queues: a due row on a queue not named is left untouched (another worker may
        consume it), and the rest are released **queue-by-queue in the given order** — every due
        row for ``queues[0]`` before any of ``queues[1]``'s — the priority cadence for the
        durable jobs table (see ``work``'s docstring)."""
        import time

        from arvel.queue.jobs import QueuedJob

        moment = now if now is not None else int(time.time())
        await self._reclaim_stuck_jobs(moment)
        due: Iterable[Any] = (
            await QueuedJob.where("available_at", "<=", moment).where_null("reserved_at").get()
        )
        if queues is not None:
            priority = {name: index for index, name in enumerate(queues)}
            due = sorted(
                (row for row in due if row.queue in priority), key=lambda r: priority[r.queue]
            )
        released = 0
        for row in due:
            # Atomic claim: rowcount == 1 means this worker won the row; 0 means another worker
            # already took it — skip it to avoid a double-dispatch.
            claim = (
                await QueuedJob.where("id", "=", row.id)
                .where_null("reserved_at")
                .update({"reserved_at": moment})
            )
            if claim.rowcount != 1:
                continue
            job = await deserialize_instance(row.payload)
            await self.push_instance(job, queue=row.queue)
            await row.delete()
            released += 1
        return released


def _queue_manager() -> Any:
    from arvel.kernel import app, has_application

    if has_application() and app().bound("queue"):
        return app().make("queue")
    return QueueManager()


class PendingChain:
    """A sequence of jobs that run **strictly in order**: job N+1 only starts after N succeeds,
    and a failure stops the chain (running ``catch`` if set) instead of continuing.

    Only the head job is dispatched now — the remaining links travel serialized on it
    (``Job.__arvel_chain__``); the worker dispatches each next link after the prior one succeeds
    (see ``QueueManager._dispatch_next_link``). This replaces pushing every link at once, which
    ran them all concurrently rather than in sequence.
    """

    def __init__(self, jobs: list[Job]) -> None:
        self.jobs = list(jobs)
        self._catch: str | None = None

    def catch(self, callback: Any) -> PendingChain:
        """Run ``callback(exc)`` once any link in the chain exhausts its retries (the chain's
        ``catch()``). ``callback`` must be a module-level function: its *qualified name* is what
        actually travels in the job payload, so a lambda/closure can't survive serialization."""
        self._catch = _qualified_name(callback)
        return self

    async def dispatch(self, *, manager: Any = None) -> Any:
        if not self.jobs:
            return None
        mgr = manager or _queue_manager()
        head, *rest = self.jobs
        head.__arvel_chain__ = [serialize_instance(j) for j in rest]
        head.__arvel_chain_catch__ = self._catch
        return await mgr.push_instance(head)


class PendingBatch:
    """A group of jobs dispatched together, with completion callbacks.

    :meth:`dispatch` creates a ``job_batches`` row up front and stamps every job with its id
    (``__arvel_batch__``) before pushing them all, so the worker can track progress/failures and
    run ``then``/``catch``/``finally`` (see ``arvel.queue.batch.apply_job_outcome``) as jobs settle
    — including two settling at the same moment (its counters are updated with a compare-and-swap
    retry loop, not a plain read-modify-write).
    """

    def __init__(self, jobs: list[Job]) -> None:
        self.jobs = list(jobs)
        self._then: list[str] = []
        self._catch: list[str] = []
        self._finally: list[str] = []
        self._name: str | None = None
        self._allow_failures = False

    def then(self, callback: Any) -> PendingBatch:
        """Run ``callback(batch)`` once every job has succeeded — never fires if a disallowed
        failure cancelled the batch first. ``callback`` must be module-level (see
        :meth:`PendingChain.catch` — a lambda/closure can't survive serialization)."""
        self._then.append(_qualified_name(callback))
        return self

    def catch(self, callback: Any) -> PendingBatch:
        """Run ``callback(batch, exc)`` on the batch's first disallowed failure (skipped when
        :meth:`allow_failures` is set)."""
        self._catch.append(_qualified_name(callback))
        return self

    def finally_(self, callback: Any) -> PendingBatch:
        """Run ``callback(batch)`` once the batch finishes — always, whether it completed cleanly
        or was cancelled by a failure."""
        self._finally.append(_qualified_name(callback))
        return self

    def name(self, name: str) -> PendingBatch:
        """A human-readable label for this batch (purely descriptive — not used as a lookup key)."""
        self._name = name
        return self

    def allow_failures(self, flag: bool = True) -> PendingBatch:
        """A failed job no longer cancels the rest of the batch: the remaining jobs keep running,
        and ``then`` still fires once every job has settled (``catch`` never fires)."""
        self._allow_failures = flag
        return self

    async def dispatch(self, *, manager: Any = None) -> Any:
        import time

        from arvel.queue.batch import Batch, JobBatch

        mgr = manager or _queue_manager()
        options = {
            "then": self._then,
            "catch": self._catch,
            "finally": self._finally,
            "name": self._name,
            "allow_failures": self._allow_failures,
        }
        row = await JobBatch.create(
            total_jobs=len(self.jobs),
            pending_jobs=len(self.jobs),
            failed_jobs=0,
            options=options,
            cancelled_at=None,
            created_at=int(time.time()),
            finished_at=None,
        )
        if not self.jobs:  # an empty batch has nothing to settle it — finish it immediately
            from arvel.queue.batch import finalize_empty_batch

            await finalize_empty_batch(row.id)
            return Batch(row.id)
        for job in self.jobs:
            job.__arvel_batch__ = row.id
        for job in self.jobs:
            await mgr.push_instance(job)
        return Batch(row.id)


class Bus:
    """Dispatch jobs as a chain (sequential) or a batch (group). ``Bus`` facade."""

    @staticmethod
    def chain(jobs: list[Job]) -> PendingChain:
        return PendingChain(jobs)

    @staticmethod
    def batch(jobs: list[Job]) -> PendingBatch:
        return PendingBatch(jobs)


def __getattr__(name: str) -> Any:
    # FailedJob pulls in arvel.database (SQLAlchemy); resolve lazily so `import arvel.queue` stays light.
    if name == "FailedJob":
        from arvel.queue.failed import FailedJob

        return FailedJob
    if name == "QueuedJob":
        from arvel.queue.jobs import QueuedJob

        return QueuedJob
    if name == "Batch":
        from arvel.queue.batch import Batch

        return Batch
    if name == "JobBatch":
        from arvel.queue.batch import JobBatch

        return JobBatch
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Batch",
    "Bus",
    "FailedJob",
    "Job",
    "JobBatch",
    "PendingBatch",
    "PendingChain",
    "QueueManager",
    "QueueSettings",
    "QueuedJob",
    "decode_instance",
    "deserialize",
    "deserialize_any",
    "deserialize_instance",
    "encode_instance",
    "run_job_with_retries",
    "serialize",
    "serialize_instance",
]
