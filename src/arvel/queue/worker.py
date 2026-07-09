"""arvel.queue.worker — the per-message execution + worker lifecycle unit (DR-0048/E14 V6).

``JobWorker`` owns the taskiq task registration (``ensure_task``, the former ``_runner``), the
per-job orchestration (``_invoke``: off-queue filter/park, batch-cancel short-circuit, DI +
middleware wrap, retry policy, chain continuation, batch outcome, unique-lock release,
``JobShouldBeReleased`` handling, worker-flag bookkeeping), and the in-process ``work()`` loop
(``_release_loop`` + worker flags). It takes its ``QueueManager`` collaborators as **narrow
injected callable seams** — no manager back-import, mirroring the ``JobRouter``/``DurableJobs``
in-file precedent, so ``arvel.queue`` stays acyclic and this module needs no import edge onto the
package ``__init__``.

The stateless retry/backoff policy (``run_job_with_retries`` and friends) are free functions here
too — they already take every dependency as a parameter, so they need no seam at all.
"""

from __future__ import annotations

import contextlib
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from arvel.queue import Job


def _backoff_for(backoff: int | list[int] | tuple[int, ...], attempt: int) -> float:
    """The delay before ``attempt``'s retry: a flat number, or per-attempt from a list (its last
    entry repeats once the list is exhausted)."""
    if isinstance(backoff, (list, tuple)):
        return backoff[min(attempt - 1, len(backoff) - 1)]
    return backoff


def _retry_should_stop(job: Job, attempt: int, tries: int) -> bool:
    """Whether to give up after this failed ``attempt`` rather than retry again: ``tries``
    exhausted, ``max_exceptions`` reached, or past ``retry_until``. ``attempt`` only advances on a
    thrown exception (a ``JobShouldBeReleased`` propagates past the retry loop and doesn't count),
    so the ``max_exceptions`` check is a genuine exception ceiling, not just an attempt one."""
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


def _resolved_label(job: Job) -> str:
    """The queue label a job class resolves to — through the bound manager's registry when an
    app is up (so spans and failure records show the routed queue), else the class attribute."""
    from arvel.kernel import app, has_application

    if has_application() and app().bound("queue"):
        label: str = app().make("queue")._queue_label(type(job), None)
        return label
    return str(getattr(job, "queue", "default"))


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


async def _record_failed_job(job: Job, exc: BaseException) -> None:
    """Persist a ``failed_jobs`` row for a job that exhausted its retries. No-op when
    no DB is bound — the ``failed()`` hook already ran, so nothing is lost and nothing crashes."""
    from arvel.kernel import app, has_application

    if not (has_application() and app().bound("db")):
        return
    from arvel.dates import Date
    from arvel.queue.failed import FailedJob
    from arvel.queue.serialization import serialize_instance

    await FailedJob.create(
        queue=_resolved_label(job),
        payload=serialize_instance(job),
        exception=f"{type(exc).__name__}: {exc}",
        failed_at=Date.now(),
    )


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
    cancel via ``asyncio.wait_for``; a sync CPU-bound ``handle()`` that never awaits won't actually
    be interrupted until it next yields — ``fail_on_timeout`` governs the retry *decision*, not
    cancellation). This is the worker's per-job execution policy.

    ``runner`` overrides how ``handle`` is called (e.g. with DI). Two retry strategies:

    - ``release`` given (a durable queue — DB/redis/amqp): try **once** this pass; on a non-final
      failure, ``await release(job, delay, attempt)`` releases the job back to the queue store
      instead of blocking this worker with an inline sleep. The next attempt happens on a later
      worker pass (``release_due_jobs`` redispatches it), resuming from ``job.__arvel_attempts__``.
    - ``release`` omitted (the in-memory/sync driver, or a direct/test call): the classic inline
      loop — ``sleep`` (injectable) between attempts, all within this one call.

    A timeout is split out from the generic failure path (``except TimeoutError`` ordered before
    ``except Exception`` — ``TimeoutError`` subclasses ``Exception``, so the order is load-bearing):
    with ``job.fail_on_timeout`` set, the **first** timeout gives up immediately (no retry); left at
    its ``False`` default, a timeout is handled by the exact same shared failed-attempt helper the
    generic exception path uses, so that path stays byte-identical to before this flag existed.

    ``on_success``/``on_exhausted`` are the worker's chain-continuation hooks (dispatch the next
    chained job / run the chain's ``catch``); optional, so direct callers (tests) are unaffected.
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

        async def _failed_attempt_released(exc: BaseException) -> None:
            if _retry_should_stop(job, attempt, tries):
                await _give_up(exc)
                return
            await release(job, _backoff_for(job.backoff, attempt), attempt)

        try:
            result = await _call()
        except TimeoutError as exc:
            if getattr(job, "fail_on_timeout", False):
                await _give_up(exc)
                return None
            await _failed_attempt_released(exc)
            return None
        except Exception as exc:
            await _failed_attempt_released(exc)
            return None
        return await _succeed(result)

    wait = sleep if sleep is not None else asyncio.sleep

    async def _failed_attempt_inline(exc: BaseException, attempt: int) -> bool:
        """``True`` -> the loop must stop (retries exhausted); ``False`` -> backed off, keep going."""
        if _retry_should_stop(job, attempt, tries):
            await _give_up(exc)
            return True
        await wait(_backoff_for(job.backoff, attempt))
        return False

    for attempt in range(1, tries + 1):
        try:
            result = await _call()
        except TimeoutError as exc:
            if getattr(job, "fail_on_timeout", False):
                await _give_up(exc)
                return None
            if await _failed_attempt_inline(exc, attempt):
                return None
        except Exception as exc:
            if await _failed_attempt_inline(exc, attempt):
                return None
        else:
            return await _succeed(result)
    return None


class _WorkerOptions:
    """Bookkeeping for one active ``work()`` run — worker-flag state (max-jobs/rest/idle
    detection). ``None`` on the worker outside an active ``work()`` call, so dispatch paths that
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
        #: (`None` = every queue). See `JobWorker._invoke`/`release_due_jobs`.
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


class JobWorker:
    """Per-message execution + worker lifecycle, split out of ``QueueManager`` (DR-0048/E14 V6).

    Takes its ``QueueManager`` collaborators as seven narrow injected callables — no manager
    back-reference, so this module never imports the package ``__init__`` at runtime:

    - ``get_broker``: the live taskiq broker accessor (``work()`` mutates ``is_worker_process`` and
      runs ``startup``/``shutdown``, so it needs the live object, not a snapshot).
    - ``push_instance``: broker push — enqueue, chain continuation, inline release.
    - ``dispatch_after``: the durable store — retry-release, off-queue park, a middleware release.
    - ``release_due``: ``DurableJobs.release_due`` for the release loop.
    - ``queue_label``: ``JobRouter.label`` — resolves a job class (+ explicit override) to its queue.
    - ``is_durable``: whether a bound DB backs the durable release rail.
    - ``get_app``: the kernel app for the DI runner (``app.call(job.handle)``) — duck-typed.
    """

    def __init__(
        self,
        *,
        get_broker: Callable[[], Any],
        push_instance: Callable[..., Awaitable[Any]],
        dispatch_after: Callable[..., Awaitable[Any]],
        release_due: Callable[..., Awaitable[int]],
        queue_label: Callable[[type, str | None], str],
        is_durable: Callable[[], bool],
        get_app: Callable[[], Any],
    ) -> None:
        self._get_broker = get_broker
        self._push_instance = push_instance
        self._dispatch_after = dispatch_after
        self._release_due = release_due
        self._queue_label = queue_label
        self._is_durable = is_durable
        self._get_app = get_app
        self._task: Any = None
        self._started = False
        self._worker_options: _WorkerOptions | None = None  # set only while work() is running
        self._worker_stop: Any = None  # the active work() run's stop/finish event

    def ensure_task(self) -> Any:
        """Register (once) and return the taskiq wrapper task both enqueue and ``work()`` share —
        the former ``QueueManager._runner``."""
        if self._task is None:
            from taskiq import Context, TaskiqDepends

            worker = self
            # `dependency=Context` explicitly (rather than an annotation taskiq would have to
            # resolve) — this module's own `from __future__ import annotations` turns the
            # parameter annotation into a string, and `Context` is only ever imported lazily
            # here, never at module scope, so taskiq couldn't look it up by name. Built once,
            # outside the `def` (not a call in the default itself), so ruff's B008 doesn't flag it.
            context_dependency = TaskiqDepends(Context)

            @self._get_broker().task  # type: ignore[untyped-decorator]  # broker is Any (lazy taskiq)
            async def _run_job(payload: str, context: Any = context_dependency) -> Any:
                # `context.message.labels["queue"]` is the *actual* queue this message was routed
                # to (set by `.with_labels(queue=label)` at push time) — `work(queues=[...])`'s
                # filter (`_invoke`) needs this, not a class-level re-derivation, since a
                # per-dispatch `queue=` override only ever lives on the message, never on the job.
                from arvel.queue.serialization import deserialize_any

                label = context.message.labels.get("queue")
                return await worker._invoke(await deserialize_any(payload), queue_label=label)

            self._task = _run_job
        return self._task

    async def _release_for_retry(self, job: Job, delay: float, attempt: int) -> None:
        """B1: release a failed job back to the queue store with ``available_at = now + delay``
        instead of an inline ``asyncio.sleep`` — this worker keeps draining other jobs meanwhile.
        ``attempt`` rides along on the job instance so the next pass (via ``release_due_jobs``)
        resumes counting from where this one left off."""
        job.__arvel_attempts__ = attempt
        # queue=None → dispatch_after resolves through _queue_label, so a route()d class
        # retries on its routed queue, not "default"
        await self._dispatch_after(delay, job, attempts=attempt)

    async def _release_job(self, job: Job, delay: float) -> None:
        """Put ``job`` back onto the queue after ``delay`` seconds (a job middleware's
        :class:`~arvel.queue.middleware.JobShouldBeReleased`) — durable (the `jobs` table) when a
        DB is bound, mirroring B1's retry-release; otherwise an inline sleep-then-repush."""
        if self._is_durable():
            await self._dispatch_after(delay, job)  # queue resolved by _queue_label inside
            return
        import asyncio

        if delay:
            await asyncio.sleep(delay)
        await self._push_instance(job)

    async def _dispatch_next_link(self, job: Job) -> None:
        """A1: on success, dispatch the next link of ``job``'s chain (if any) — the remaining
        chain travels serialized on the job itself (``__arvel_chain__``, set by
        ``PendingChain.dispatch``/carried forward here), so each link only runs after the prior
        one succeeds."""
        chain: list[str] | None = getattr(job, "__arvel_chain__", None)
        if not chain:
            return
        payload, *rest = chain
        from arvel.queue.serialization import deserialize_instance

        next_job = await deserialize_instance(payload)
        next_job.__arvel_chain__ = rest
        next_job.__arvel_chain_catch__ = job.__arvel_chain_catch__
        await self._push_instance(next_job)

    async def _run_chain_catch(self, job: Job, exc: BaseException) -> None:
        """A1: a chain's ``catch`` (if set) fires once a link exhausts its retries, and the rest
        of the chain never runs. ``catch`` must be a module-level callable (its qualified name is
        what actually travels in the payload — a closure/lambda can't survive serialization)."""
        catch_ref = getattr(job, "__arvel_chain_catch__", None)
        if not catch_ref:
            return
        import inspect

        from arvel.queue.serialization import _load  # pyright: ignore[reportPrivateUsage]

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
            # `ensure_task`'s task) when known — a per-dispatch `queue=` override (e.g.
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
                    await self._dispatch_after(0, job, queue=label)
                    return None
                # No DB to park into and no other consumer: an inline broker is the sole executor,
                # so running the job here is the only way an already-acked delivery isn't silently
                # lost. Ratified for this degenerate (restricted worker + memory broker + no DB)
                # configuration only — see DR-0049. Fall through to execute it.

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
        resolved_app = self._get_app()
        if resolved_app is not None and hasattr(resolved_app, "call"):
            runner = lambda: resolved_app.call(job.handle)  # noqa: E731
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
                    released = await self._release_due(queues=queues)
                except Exception:
                    # a transient DB hiccup must not kill the worker — but a permanently
                    # broken DB silently stalling delayed/retry jobs must be visible
                    from arvel.kernel.logging import LogManager

                    LogManager().channel("queue").warning("release_due_jobs_failed", exc_info=True)
            self._on_release_tick(released)

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

        self.ensure_task()  # register the wrapper task on the broker
        broker = self._get_broker()
        # A same-process dispatch may have started the broker in client mode; taskiq-aio-pika's
        # startup() isn't idempotent, so shut it down first and restart cleanly in worker mode.
        if self._started:
            await broker.shutdown()
            self._started = False
        # Must be set before startup: a consuming broker (e.g. taskiq-aio-pika) only declares its
        # read connection/consumer when is_worker_process is set, else listen() raises.
        broker.is_worker_process = True
        await broker.startup()
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
            if isinstance(broker, InMemoryBroker):
                # runs jobs inline on dispatch and can't be listened to; just wait for a stop condition.
                await finish.wait()
            else:
                from taskiq.receiver import Receiver

                await Receiver(broker).listen(finish)  # cooperative: drains in-flight work
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


__all__ = [
    "JobWorker",
    "run_job_with_retries",
]
