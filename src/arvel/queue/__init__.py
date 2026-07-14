"""arvel.queue — jobs + queue on **taskiq** (mandated engine; the ``[queue]`` extra).

``Job`` is the app's base (``await MyJob.dispatch(...)``); ``QueueManager`` wraps a real
taskiq broker selected from the ``queue`` config (``memory`` core / ``redis`` via ``[queue-redis]`` /
``amqp`` via ``[queue-amqp]``), serializing the job to JSON (no closures) and running ``handle()``
(with container DI) in the worker. Model args are
serialized as ``(class, pk)`` refs and re-fetched fresh in the worker (``model_ref``). taskiq
is imported lazily so ``import arvel`` stays light. Bus/scheduler/broadcasting are follow-ons.
Grounded in knowledge/port/12-queues.md.

The serialization codec (``queue/serialization.py``) and the per-message execution + worker
lifecycle (``JobWorker`` in ``queue/worker.py``) are split out of this module (DR-0048/E14 V6) —
this file is now the broker-selection / route / durable / enqueue / admin **facade**: ``Job``,
``Bus``/``PendingChain``/``PendingBatch``, and ``QueueManager`` (which constructs and delegates to
a ``JobWorker``) stay here. Every previously-defined-here name is re-exported below so the public
+ intra-package ``from arvel.queue import X`` surface is unchanged.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from arvel.kernel import Settings

# Re-exports of every name this module used to define itself, now split out into
# `queue/serialization.py` (the codec, DR-0048/E14 V6) and `queue/worker.py` (the worker loop) —
# `X as X` keeps the public + intra-package `from arvel.queue import X` surface byte-identical.
# `_load`/`_qualified_name` are the private names siblings (middleware.py/batch.py/broadcast.py/
# listener.py/failed.py) still reach for this way.
from arvel.queue.serialization import _load as _load  # pyright: ignore[reportPrivateUsage]
from arvel.queue.serialization import (
    _qualified_name as _qualified_name,  # pyright: ignore[reportPrivateUsage]
)
from arvel.queue.serialization import decode_instance as decode_instance
from arvel.queue.serialization import deserialize as deserialize
from arvel.queue.serialization import deserialize_any as deserialize_any
from arvel.queue.serialization import deserialize_instance as deserialize_instance
from arvel.queue.serialization import encode_instance as encode_instance
from arvel.queue.serialization import model_ref as model_ref
from arvel.queue.serialization import serialize as serialize
from arvel.queue.serialization import serialize_instance as serialize_instance
from arvel.queue.worker import JobWorker
from arvel.queue.worker import (
    _stop_on_memory as _stop_on_memory,  # pyright: ignore[reportPrivateUsage]
)
from arvel.queue.worker import (
    _WorkerOptions as _WorkerOptions,  # pyright: ignore[reportPrivateUsage]
)
from arvel.queue.worker import run_job_with_retries as run_job_with_retries
from arvel.support.manager import Manager

if TYPE_CHECKING:
    from arvel.queue.batch import Batch as Batch
    from arvel.queue.batch import JobBatch as JobBatch
    from arvel.queue.failed import FailedJob as FailedJob
    from arvel.queue.jobs import QueuedJob as QueuedJob


class QueueDriver(StrEnum):
    """The built-in queue brokers — a typed set for ``queue.default``. A ``StrEnum`` (not a
    ``Literal``): flows through the string-keyed driver dispatch, so a custom broker registered via
    ``QueueManager.extend`` stays a plain ``str`` — the registry stays open."""

    MEMORY = "memory"
    REDIS = "redis"
    AMQP = "amqp"


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


class Job:
    """Base job: subclass and implement ``handle()``."""

    queue: str = "default"
    #: Defer enqueue until the surrounding DB transaction commits (dropped on rollback);
    #: immediate when no transaction is open. Per-call form: :meth:`dispatch_after_commit`.
    after_commit: bool = False
    tries: int = 3
    backoff: int | list[int] = 5
    timeout: int = 60
    #: A timed-out attempt (`asyncio.wait_for` past `timeout`) normally retries like any other
    #: failure. Set `True` to give up on the **first** timeout instead — straight to `failed_jobs`,
    #: no retry (E14/V1). Governs the retry *decision* only: a sync CPU-bound `handle()` that never
    #: awaits won't actually be interrupted until it next yields (cooperative cancel, not fixed here).
    fail_on_timeout: bool = False
    #: Visibility-timeout override (seconds) for this job's class; ``None`` -> the
    #: ``queue.retry_after`` config default (see `DurableJobs._reclaim_stuck`).
    retry_after: int | None = None
    #: Cap on *thrown* exceptions before the job is failed — a tighter ceiling than `tries`. A
    #: `JobShouldBeReleased` (a middleware or handler putting the job back on the queue) is not an
    #: exception: it never counts toward this or `tries`.
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
    __arvel_log_context__: dict[str, Any] | None = None  # dispatcher's bound log context, propagated

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


class JobRouter:
    """Resolves a job class to its queue name — the routing concern, split out of the coordinator.

    Precedence: an explicit ``queue=`` at dispatch > a ``queue`` attribute on the class > this
    registry > ``"default"``. Holds no broker/store/worker state, so it's a pure, testable unit.
    """

    def __init__(self) -> None:
        self._routes: dict[type, str] = {}  # per-class routing (last write wins)

    def route(self, job_cls: type, queue: str) -> None:
        self._routes[job_cls] = queue

    def label(self, job_cls: type, explicit: str | None) -> str:
        if explicit:
            return explicit
        for klass in job_cls.__mro__:
            if klass is Job:
                break  # Job.queue = "default" is the fallback, not a declaration
            declared = klass.__dict__.get("queue")
            if isinstance(declared, str):
                return declared
        routed = self._routes.get(job_cls)
        return routed if routed is not None else "default"


class DurableJobs:
    """The durable jobs-table store, split out of the coordinator: delayed / retry-release rows
    persisted to the ``jobs`` table, reserved with a visibility timeout, and released onto the
    broker when due. Depends only on routing, a push callable, and the retry-after setting — no
    back-reference to the manager.
    """

    def __init__(
        self,
        router: JobRouter,
        push: Callable[..., Awaitable[Any]],
        retry_after: Callable[[], int],
    ) -> None:
        self._router = router
        self._push = push  # the broker-push (QueueManager.push_instance) — a plain callable
        self._retry_after = retry_after

    async def store(
        self, delay: float, job: Job, *, queue: str | None = None, attempts: int = 0
    ) -> Any:
        """Persist a job to the ``jobs`` table with ``available_at = now + delay`` — the durable
        delayed/retry rail. ``attempts`` carries the real attempt count across a retry-release.

        ``available_at`` is an integer unix-second column, so a fractional ``delay`` (a sub-second
        ``Job.backoff``, e.g. ``0.2``) needs rounding — **up** (``ceil``), never truncation:
        ``int(0.2)`` floors to ``0``, silently collapsing any positive sub-second delay into "due
        immediately" and defeating the whole point of a backoff. Rounding up instead guarantees a
        positive ``delay`` always lands strictly in the future (never earlier than requested); a
        zero delay stays due now, exactly as ``dispatch_after(0, ...)`` (immediate enqueue) needs.
        """
        import math
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
            queue=self._router.label(type(job), queue),
            payload=serialize_instance(job),
            attempts=attempts,
            available_at=now + math.ceil(delay),
            created_at=now,
        )

    async def _reclaim_stuck(self, moment: int) -> None:
        """Visibility timeout: a row whose ``reserved_until`` deadline has passed means the worker
        that claimed it died mid-flight — free it so another worker retakes it.

        ``reserved_until`` (``reserved_at + effective retry_after``) is computed once at claim time,
        so this is a single **indexed** filter with no per-row payload decode (F-027) — the reclaim
        cost is O(actually-stuck), not O(all-reserved)."""
        from arvel.queue.jobs import QueuedJob

        overdue = (
            await QueuedJob.where_not_null("reserved_until")
            .where("reserved_until", "<=", moment)
            .get()
        )
        for row in overdue:
            await (
                QueuedJob.where("id", "=", row.id)
                .where("reserved_until", "=", row.reserved_until)  # optimistic: skip if re-claimed
                .update({"reserved_at": None, "reserved_until": None})
            )
        # Legacy safety net: rows reserved before `reserved_until` existed (a migration boundary)
        # carry a NULL deadline. Reclaim them conservatively at the default window — no decode.
        legacy = (
            await QueuedJob.where_not_null("reserved_at")
            .where_null("reserved_until")
            .where("reserved_at", "<=", moment - self._retry_after())
            .get()
        )
        for row in legacy:
            await (
                QueuedJob.where("id", "=", row.id)
                .where("reserved_at", "=", row.reserved_at)
                .update({"reserved_at": None})
            )

    async def release_due(self, now: int | None = None, *, queues: list[str] | None = None) -> int:
        """Reclaim timed-out reservations, then push every due row onto the broker and delete it.
        ``queues`` restricts + orders release queue-by-queue in the given priority order."""
        import time

        from arvel.queue.jobs import QueuedJob

        moment = now if now is not None else int(time.time())
        await self._reclaim_stuck(moment)
        due: Iterable[Any] = (
            await QueuedJob.where("available_at", "<=", moment).where_null("reserved_at").get()
        )
        if queues is not None:
            priority = {name: index for index, name in enumerate(queues)}
            due = sorted(
                (row for row in due if row.queue in priority), key=lambda r: priority[r.queue]
            )
        released = 0
        default_retry_after = self._retry_after()
        for row in due:
            # Atomic claim FIRST (rowcount == 1 means this worker won the row; 0 means another took
            # it — skip, no double-dispatch). Claim with the DEFAULT visibility window, then refine
            # to the job's own retry_after after decoding. Claiming before the decode is deliberate:
            # a poison-pill payload (undeserializable) is then PARKED as reserved instead of staying
            # `available` and re-blocking the whole due-loop on every tick.
            claim = (
                await QueuedJob.where("id", "=", row.id)
                .where_null("reserved_at")
                .update(
                    {"reserved_at": moment, "reserved_until": moment + int(default_retry_after)}
                )
            )
            if claim.rowcount != 1:
                continue
            try:
                job = await deserialize_instance(row.payload)
            except Exception:
                # can't decode this row — leave it parked (reserved) so it doesn't re-block siblings;
                # the reclaim frees it after the default window and it retries (or ages into failure).
                from arvel.kernel.logging import LogManager

                LogManager().channel("queue").warning(
                    "undeserializable_job", job_id=row.id, queue=row.queue, exc_info=True
                )
                continue
            override = getattr(job, "retry_after", None)
            if override is not None:
                # refine the visibility deadline to the job's own window (still before any push, so a
                # crash here only re-queues an unpushed job — never double-executes a running one)
                await QueuedJob.where("id", "=", row.id).where("reserved_at", "=", moment).update(
                    {"reserved_until": moment + int(override)}
                )
            await self._push(job, queue=row.queue)
            await row.delete()
            released += 1
        return released


class QueueManager(Manager):
    """Pushes jobs onto a config-selected taskiq broker (the Manager 'driver': ``memory``/``redis``/
    ``amqp``) and runs them via a single wrapper task. Broker selection / route / durable / enqueue /
    admin facade — the per-message execution + worker lifecycle live in :class:`~arvel.queue.worker.JobWorker`
    (constructed below, DR-0048/E14 V6), which this class delegates to."""

    def __init__(self, app: Any = None, broker: Any = None) -> None:
        super().__init__(app)
        self._broker = broker  # an explicit broker passed in wins over the config-selected one
        self._router = JobRouter()  # per-class queue routing, split out of this coordinator
        self._durable = DurableJobs(  # the jobs-table store, also split out
            self._router,
            self.push_instance,
            lambda: self._settings(QueueSettings).retry_after,
        )
        self._worker = JobWorker(
            get_broker=lambda: self.broker,
            push_instance=self.push_instance,
            dispatch_after=self.dispatch_after,
            release_due=self._durable.release_due,
            queue_label=self._queue_label,
            is_durable=self._is_durable,
            get_app=lambda: self.app,
        )

    @property
    def _started(self) -> bool:
        """The broker-startup once-guard — owned by `JobWorker` (shared between `push`/
        `push_instance` here and `JobWorker.work()`); exposed here too since it's this class's own
        enqueue paths that read/write it most."""
        return self._worker._started  # pyright: ignore[reportPrivateUsage]

    @_started.setter
    def _started(self, value: bool) -> None:
        self._worker._started = value  # pyright: ignore[reportPrivateUsage]

    def route(self, job_cls: type, *, queue: str) -> None:
        """Route ``job_cls`` to ``queue`` by default — declared once (a provider), not on the
        class. Precedence: an explicit ``queue=`` at dispatch > a ``queue`` attribute declared
        on the class itself > this registry > ``"default"``. Re-registering replaces."""
        self._router.route(job_cls, queue)

    def _queue_label(self, job_cls: type, explicit: str | None) -> str:
        return self._router.label(job_cls, explicit)

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
        task = self._worker.ensure_task()
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
        from arvel.queue.failed import failed_jobs as _failed_jobs

        return await _failed_jobs()

    async def retry_failed(self, failed_id: str | None = None) -> list[Any]:
        """Re-dispatch failed jobs — one by id, or every one. Returns
        the records that were retried (each is re-pushed and its record deleted)."""
        from arvel.queue.failed import retry_failed as _retry_failed

        return await _retry_failed(failed_id)

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

        Delegates to :meth:`~arvel.queue.worker.JobWorker.work` — see there for the full
        behavior (queue filtering/priority, worker flags, signal handling)."""
        await self._worker.work(
            queues,
            release_interval=release_interval,
            max_jobs=max_jobs,
            max_time=max_time,
            stop_when_empty=stop_when_empty,
            rest=rest,
            memory=memory,
        )

    async def push_instance(self, job: Job, *, queue: str | None = None) -> Any:
        task = self._worker.ensure_task()
        if not self._started:
            await self.broker.startup()
            self._started = True
        label = self._queue_label(type(job), queue)
        return await task.kicker().with_labels(queue=label).kiq(serialize_instance(job))

    async def dispatch_after(
        self, delay: float, job: Job, *, queue: str | None = None, attempts: int = 0
    ) -> Any:
        """Delay a job: persist it to the ``jobs`` table with ``available_at = now + delay``
        instead of enqueuing now. A worker/scheduler calls :meth:`release_due_jobs` to push the due
        ones. Durable (survives restart); needs a DB. ``attempts`` carries the real attempt count
        across a retry-release."""
        return await self._durable.store(delay, job, queue=queue, attempts=attempts)

    async def release_due_jobs(
        self, now: int | None = None, *, queues: list[str] | None = None
    ) -> int:
        """Reclaim any visibility-timed-out reservations, then push every stored job whose
        ``available_at`` has passed onto the broker and delete its row. Returns how many were
        released. A worker (``queue:work``) / scheduler calls this periodically. ``queues`` (from an
        active ``work(queues=[...])`` run) restricts + orders release queue-by-queue in that
        priority order."""
        return await self._durable.release_due(now, queues=queues)


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
    (see ``JobWorker._dispatch_next_link``). This replaces pushing every link at once, which
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
    "QueueDriver",
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
