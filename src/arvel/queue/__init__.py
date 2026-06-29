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
from typing import TYPE_CHECKING, Any, cast

from arvel.kernel import Settings
from arvel.support.manager import Manager

if TYPE_CHECKING:
    from arvel.queue.failed import FailedJob as FailedJob
    from arvel.queue.jobs import QueuedJob as QueuedJob


class QueueSettings(Settings):
    """Typed, validated view over the ``queue`` config section (DR-0016).

    ``default`` names the broker driver — ``memory`` (core), ``redis`` (the ``[queue-redis]`` extra),
    or ``amqp`` (RabbitMQ/any AMQP broker, the ``[queue-amqp]`` extra). ``url`` is the single DSN for
    the active driver (a ``redis://`` or ``amqp://`` endpoint); ``memory`` ignores it.
    """

    __config_key__ = "queue"
    default: str = "memory"
    url: str = "redis://localhost:6379/0"


def _qualified_name(cls: type) -> str:
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


def serialize(job_cls: type, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    import msgspec

    return msgspec.json.encode(
        {
            "job": _qualified_name(job_cls),
            "args": [model_ref(a) for a in args],
            "kwargs": {k: model_ref(v) for k, v in kwargs.items()},
            "_trace": _trace_carrier(),
        }
    ).decode()


async def deserialize(payload: str) -> Job:
    import msgspec

    data = msgspec.json.decode(payload)
    job_cls = _load(str(data["job"]))
    args = [await _rehydrate(a) for a in data["args"]]
    kwargs = {k: await _rehydrate(v) for k, v in data["kwargs"].items()}
    job: Job = job_cls(*args, **kwargs)
    job.__arvel_trace__ = data.get("_trace")  # type: ignore[attr-defined]  # parent trace for the job span
    return job


def serialize_instance(job: Job) -> str:
    """Serialize an already-constructed job by its attribute state (Bus dispatches instances).

    Model-valued attributes become ``(class, pk)`` refs, exactly as for arg serialization.
    """
    import msgspec

    state = {key: model_ref(val) for key, val in vars(job).items() if key != "__arvel_trace__"}
    return msgspec.json.encode(
        {"job": _qualified_name(type(job)), "state": state, "_trace": _trace_carrier()}
    ).decode()


async def deserialize_instance(payload: str) -> Job:
    import msgspec

    data = msgspec.json.decode(payload)
    job_cls = _load(str(data["job"]))
    job: Job = job_cls.__new__(job_cls)  # bypass __init__; restore attribute state directly
    for key, val in cast("dict[str, Any]", data["state"]).items():
        setattr(job, key, await _rehydrate(val))
    job.__arvel_trace__ = data.get("_trace")  # type: ignore[attr-defined]  # parent trace for the job span
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
    """Base job: subclass and implement ``handle()`` (Laravel ``Job``/``ShouldQueue``)."""

    queue: str = "default"
    tries: int = 3
    backoff: int | list[int] = 5
    timeout: int = 60

    async def handle(self) -> Any:
        raise NotImplementedError(f"{type(self).__name__} must implement handle()")

    async def failed(self, exc: BaseException) -> None:
        """Hook invoked when the job exhausts its retries (override to alert/log)."""

    @classmethod
    async def dispatch(cls, *args: Any, **kwargs: Any) -> Any:
        from arvel.kernel import app, has_application

        manager = (
            app().make("queue") if has_application() and app().bound("queue") else QueueManager()
        )
        return await manager.push(cls, args, kwargs)

    @classmethod
    async def dispatch_after(cls, delay: float, *args: Any, **kwargs: Any) -> Any:
        """Dispatch this job to run after ``delay`` seconds (Laravel ``dispatch()->delay()``).
        Durable, DB-backed — see :meth:`QueueManager.dispatch_after`."""
        from arvel.kernel import app, has_application

        manager = (
            app().make("queue") if has_application() and app().bound("queue") else QueueManager()
        )
        return await manager.dispatch_after(delay, cls(*args, **kwargs))


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
    # A traceparent captured at dispatch (rides in the payload) makes this job a child of the
    # dispatching request even across a separate worker process. No carrier → ambient nesting
    # (the inline case) or a fresh root (a standalone worker).
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
        span.set_attribute("messaging.destination.name", str(getattr(job, "queue", "default")))
        span.set_attribute("code.namespace", type(job).__module__)
        span.set_attribute("code.function", name)
        yield span


async def run_job_with_retries(job: Job, *, runner: Any = None, sleep: Any = None) -> Any:
    """Run a job, retrying on failure up to ``job.tries`` with ``job.backoff`` between attempts;
    invoke ``job.failed(exc)`` once the attempts are exhausted. This is the worker's per-job
    execution policy. ``runner`` overrides how ``handle`` is called (e.g. with DI); ``sleep``
    is injectable for tests."""
    import asyncio

    invoke = runner if runner is not None else job.handle
    wait = sleep if sleep is not None else asyncio.sleep
    tries = max(1, int(getattr(job, "tries", 1)))
    backoff = job.backoff
    for attempt in range(1, tries + 1):
        try:
            return await invoke()
        except Exception as exc:
            if attempt >= tries:
                await job.failed(exc)
                await _record_failed_job(job, exc)
                return None
            delay = (
                backoff[min(attempt - 1, len(backoff) - 1)]
                if isinstance(backoff, (list, tuple))
                else backoff
            )
            await wait(delay)
    return None


async def _record_failed_job(job: Job, exc: BaseException) -> None:
    """Persist a ``failed_jobs`` row for a job that exhausted its retries (Laravel parity). No-op when
    no DB is bound — the ``failed()`` hook already ran, so nothing is lost and nothing crashes."""
    from arvel.kernel import app, has_application

    if not (has_application() and app().bound("db")):
        return
    from arvel.dates import Date
    from arvel.queue.failed import FailedJob

    await FailedJob.create(
        queue=getattr(job, "queue", "default"),
        payload=serialize_instance(job),
        exception=f"{type(exc).__name__}: {exc}",
        failed_at=Date.now(),
    )


class QueueManager(Manager):
    """Pushes jobs onto a config-selected taskiq broker (the Manager 'driver': ``memory``/``redis``/
    ``amqp``) and runs them via a single wrapper task."""

    def __init__(self, app: Any = None, broker: Any = None) -> None:
        super().__init__(
            app
        )  # Manager: sets up driver resolution/cache + the _settings(app) helper
        self._broker = broker  # an explicit broker passed in wins over the config-selected one
        self._task: Any = None
        self._started = False

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
        # An explicit broker (passed to __init__) wins; otherwise the config-selected driver, built +
        # cached by Manager.driver() (memory by default → no app/config still yields an InMemoryBroker).
        return self._broker if self._broker is not None else self.driver()

    async def _invoke(self, job: Job) -> Any:
        # Worker execution: container-DI into handle() when an app is present, with the
        # job's retry/backoff/failed() policy enforced around it.
        runner = None
        if self.app is not None and hasattr(self.app, "call"):
            runner = lambda: self.app.call(job.handle)  # noqa: E731
        with _job_span(job):
            return await run_job_with_retries(job, runner=runner)

    def _runner(self) -> Any:
        if self._task is None:
            manager = self

            @self.broker.task  # type: ignore[untyped-decorator]  # broker is Any (lazy taskiq)
            async def _run_job(payload: str) -> Any:
                return await manager._invoke(await deserialize_any(payload))

            self._task = _run_job
        return self._task

    async def push(
        self,
        job_cls: type,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        *,
        queue: str | None = None,
    ) -> Any:
        task = self._runner()
        if not self._started:
            await self.broker.startup()
            self._started = True
        label = queue or getattr(job_cls, "queue", "default")
        return await task.kicker().with_labels(queue=label).kiq(serialize(job_cls, args, kwargs))

    async def work(self, queues: list[str] | None = None, *, release_interval: float = 1.0) -> None:
        """Run an in-process worker: consume + execute jobs from the broker until cancelled.

        Backs ``arvel queue:work``. For production scale, run taskiq's own worker process
        against the broker; this is the convenient in-process equivalent.
        """
        import asyncio

        from taskiq import InMemoryBroker

        self._runner()  # register the wrapper task on the broker
        # If a same-process dispatch already started the broker in *client* mode, shut it down first:
        # taskiq-aio-pika's startup() isn't idempotent (it reopens write_conn, orphaning the old one),
        # and a client-mode start never declared the consumer. Restart cleanly in worker mode.
        if self._started:
            await self.broker.shutdown()
            self._started = False
        # Mark the broker as a worker BEFORE startup: a consuming broker (e.g. taskiq-aio-pika) only
        # declares its read connection + consumer queue when ``is_worker_process`` is set, so without
        # this a real AMQP worker raises "Call startup before starting listening" on listen().
        self.broker.is_worker_process = True
        await self.broker.startup()
        self._started = True
        # Release any delayed jobs whose time has come (dispatch_after) alongside consuming the broker.
        releaser = asyncio.create_task(self._release_loop(release_interval))
        try:
            if isinstance(self.broker, InMemoryBroker):
                # the in-memory broker runs jobs inline on dispatch and cannot be listened to;
                # the worker's only ongoing job is releasing due delayed jobs.
                await releaser
            else:
                from taskiq.receiver import Receiver

                finish = asyncio.Event()  # taskiq's Receiver.listen requires a stop event
                try:
                    await Receiver(self.broker).listen(finish)
                finally:
                    finish.set()
        finally:
            releaser.cancel()

    async def _release_loop(self, interval: float = 1.0) -> None:
        """Periodically push due delayed jobs onto the broker. A transient error never kills the worker."""
        import asyncio
        import contextlib

        from arvel.kernel import app, has_application

        while True:
            await asyncio.sleep(interval)
            if has_application() and app().bound("db"):
                # a transient DB hiccup must not kill the worker — try again next tick
                with contextlib.suppress(Exception):
                    await self.release_due_jobs()

    async def push_instance(self, job: Job, *, queue: str | None = None) -> Any:
        task = self._runner()
        if not self._started:
            await self.broker.startup()
            self._started = True
        label = queue or getattr(job, "queue", "default")
        return await task.kicker().with_labels(queue=label).kiq(serialize_instance(job))

    async def dispatch_after(self, delay: float, job: Job, *, queue: str | None = None) -> Any:
        """Delay a job (Laravel ``dispatch()->delay()``): persist it to the ``jobs`` table with
        ``available_at = now + delay`` instead of enqueuing now. A worker/scheduler calls
        :meth:`release_due_jobs` to push the due ones. Durable (survives restart); needs a DB."""
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
            queue=queue or getattr(job, "queue", "default"),
            payload=serialize_instance(job),
            attempts=0,
            available_at=now + int(delay),
            created_at=now,
        )

    async def release_due_jobs(self, now: int | None = None) -> int:
        """Push every stored job whose ``available_at`` has passed onto the broker and delete its row.
        Returns how many were released. A worker (``queue:work``) / scheduler calls this periodically."""
        import time

        from arvel.queue.jobs import QueuedJob

        moment = now if now is not None else int(time.time())
        due = await QueuedJob.where("available_at", "<=", moment).where_null("reserved_at").get()
        released = 0
        for row in due:
            # Atomic claim: set reserved_at only while it's still null. rowcount == 1 means THIS worker
            # won the row; 0 means another worker (or release pass) already took it — skip, no
            # double-dispatch. The `reserved_at IS NULL` guard + per-row write atomicity is the lock.
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
    """A sequence of jobs dispatched in order (each is queued after the prior is enqueued)."""

    def __init__(self, jobs: list[Job]) -> None:
        self.jobs = list(jobs)

    async def dispatch(self, *, manager: Any = None) -> None:
        mgr = manager or _queue_manager()
        for job in self.jobs:
            await mgr.push_instance(job)


class PendingBatch:
    """A group of jobs dispatched together; returns each push's handle."""

    def __init__(self, jobs: list[Job]) -> None:
        self.jobs = list(jobs)

    async def dispatch(self, *, manager: Any = None) -> list[Any]:
        mgr = manager or _queue_manager()
        return [await mgr.push_instance(job) for job in self.jobs]


class Bus:
    """Dispatch jobs as a chain (sequential) or a batch (group). Laravel ``Bus`` facade."""

    @staticmethod
    def chain(jobs: list[Job]) -> PendingChain:
        return PendingChain(jobs)

    @staticmethod
    def batch(jobs: list[Job]) -> PendingBatch:
        return PendingBatch(jobs)


def __getattr__(name: str) -> Any:
    # Lazy re-export: FailedJob pulls in arvel.database (SQLAlchemy); resolve it only on access so
    # `import arvel.queue` stays light (import-linter G2).
    if name == "FailedJob":
        from arvel.queue.failed import FailedJob

        return FailedJob
    if name == "QueuedJob":
        from arvel.queue.jobs import QueuedJob

        return QueuedJob
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Bus",
    "FailedJob",
    "Job",
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
