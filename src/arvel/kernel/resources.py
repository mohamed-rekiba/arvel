"""Unified resource lifecycle & health checking (DR-0039).

A :class:`ResourceManager` collects the app's external dependencies — anything satisfying the
``contracts.Resource`` Protocol (database, cache, queue, …) — and drives them through one lifecycle:

- **startup** — connect + health-check every resource **concurrently** (per-op timeout + bounded
  retries), emit a structured report, and decide *abort* (a critical resource failed) vs *degrade*.
- **check_all** — the health phase alone, reused by the ``/health`` endpoint (no connect, no retries).
- **shutdown** — disconnect the connected resources **concurrently**; idempotent, best-effort,
  never raises.

The manager lives in the kernel (import-light: asyncio + stdlib + ``contracts``), so the lifespan
seam can drive it without a kernel→capability edge. Resources are pushed in by capability providers
(``app.resources.register(...)``) — core never learns the concrete set (DR-0026).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, replace
from time import perf_counter
from typing import TypeVar

from arvel.contracts import HealthResult, HealthStatus, ManagedLifecycle, Resource

_T = TypeVar("_T")

# Worst-status rollup. StrEnum orders by string value ("failed" < "ok"), which is *not* severity —
# so aggregate status uses this explicit ranking, not max() over the enum.
_SEVERITY = {HealthStatus.OK: 0, HealthStatus.DEGRADED: 1, HealthStatus.FAILED: 2}


def _worst(statuses: Iterable[HealthStatus]) -> HealthStatus:
    return max(statuses, key=_SEVERITY.__getitem__, default=HealthStatus.OK)


def _err(exc: BaseException) -> str:
    if isinstance(exc, TimeoutError):
        return "timeout"
    return f"{type(exc).__name__}: {exc}"


class StartupAborted(RuntimeError):
    """Raised by :meth:`ResourceManager.startup` when a *critical* resource failed its check — boot
    must not proceed. Carries the :class:`HealthReport` so the caller can log/inspect it."""

    def __init__(self, report: HealthReport) -> None:
        failed = ", ".join(r.name for r, res in report.entries if res.status is HealthStatus.FAILED)
        super().__init__(f"resource startup aborted — critical resource(s) failed: {failed}")
        self.report = report


@dataclass(frozen=True, slots=True)
class HealthReport:
    """Aggregate outcome of checking every registered resource. Rolls per-resource
    :class:`HealthResult`s up into counts, a worst-case status, and an abort/degrade decision."""

    entries: tuple[tuple[Resource, HealthResult], ...]

    @property
    def results(self) -> dict[str, HealthResult]:
        return {r.name: res for r, res in self.entries}

    @property
    def status(self) -> HealthStatus:
        return _worst(res.status for _, res in self.entries)

    @property
    def ok(self) -> int:
        return sum(res.status is HealthStatus.OK for _, res in self.entries)

    @property
    def degraded(self) -> int:
        return sum(res.status is HealthStatus.DEGRADED for _, res in self.entries)

    @property
    def failed(self) -> int:
        return sum(res.status is HealthStatus.FAILED for _, res in self.entries)

    @property
    def critical_failed(self) -> bool:
        return any(r.critical and res.status is HealthStatus.FAILED for r, res in self.entries)

    @property
    def healthy(self) -> bool:
        """True when nothing *critical* has failed — the readiness verdict (a degraded
        non-critical resource is still healthy)."""
        return not self.critical_failed

    @property
    def decision(self) -> str:
        if self.critical_failed:
            return "abort"
        if self.failed or self.degraded:
            return "degraded"
        return "ready"


class ResourceManager:
    """Owns the connect → health-check → disconnect lifecycle for all registered resources.

    Timeouts/retries are the policy knobs: ``connect_timeout``/``check_timeout`` bound each op so one
    slow dependency can't hang boot; ``boot_retries`` retries transient cold-infra failures on the
    startup gate only (``check_all`` for ``/health`` uses zero — current truth, fast).
    """

    def __init__(
        self,
        *,
        connect_timeout: float = 10.0,
        check_timeout: float = 5.0,
        shutdown_timeout: float = 10.0,
        boot_retries: int = 2,
    ) -> None:
        self._resources: list[Resource] = []
        self._names: set[str] = set()
        self._connected: set[Resource] = set()
        self._closed = False
        self._connect_timeout = connect_timeout
        self._check_timeout = check_timeout
        self._shutdown_timeout = shutdown_timeout
        self._boot_retries = boot_retries

    # --- registration ------------------------------------------------------
    def register(self, resource: Resource) -> None:
        """Add a resource to the lifecycle. Registration order is dependency order (it mirrors
        provider boot order); a duplicate ``name`` replaces the prior registration."""
        if resource.name in self._names:
            self._resources = [r for r in self._resources if r.name != resource.name]
        self._resources.append(resource)
        self._names.add(resource.name)

    @property
    def resources(self) -> tuple[Resource, ...]:
        return tuple(self._resources)

    # --- startup -----------------------------------------------------------
    async def startup(self) -> HealthReport:
        """Connect + health-check every resource **concurrently**, log the report, and enforce the
        abort/degrade decision: a failed *critical* resource rolls back everything already connected
        and raises :class:`StartupAborted`; otherwise boot proceeds (degraded non-criticals logged)."""
        self._closed = False
        report = HealthReport(
            tuple(
                zip(
                    self._resources,
                    await asyncio.gather(*(self._bring_up(r) for r in self._resources)),
                    strict=True,
                )
            )
        )
        self._log_report(report)
        if report.critical_failed:
            await self.shutdown()  # roll back the resources that did connect
            raise StartupAborted(report)
        return report

    async def _bring_up(self, resource: Resource) -> HealthResult:
        """Per-resource pipeline: connect (if it has a lifecycle) then check. Never raises — a
        failure anywhere becomes a FAILED result, so one bad resource can't abort the gather."""
        started = perf_counter()
        try:
            if isinstance(resource, ManagedLifecycle):
                await self._retry(resource.connect, self._connect_timeout, self._boot_retries)
                self._connected.add(resource)
        except Exception as exc:
            return HealthResult(HealthStatus.FAILED, (perf_counter() - started) * 1000, _err(exc))
        return await self._check(resource, self._boot_retries)

    # --- runtime checks (reused by /health) --------------------------------
    async def check_all(self, *, retries: int = 0) -> HealthReport:
        """Health-check every resource concurrently, *without* connecting — the runtime readiness
        probe. Zero retries by default (current truth). Does not log (it's polled)."""
        results = await asyncio.gather(*(self._check(r, retries) for r in self._resources))
        return HealthReport(tuple(zip(self._resources, results, strict=True)))

    async def _check(self, resource: Resource, retries: int) -> HealthResult:
        started = perf_counter()
        try:
            result = await self._retry(resource.check, self._check_timeout, retries)
        except Exception as exc:
            return HealthResult(HealthStatus.FAILED, (perf_counter() - started) * 1000, _err(exc))
        if result.latency_ms == 0.0:  # resource didn't self-report → measure it
            return replace(result, latency_ms=(perf_counter() - started) * 1000)
        return result

    # --- shutdown ----------------------------------------------------------
    async def shutdown(self) -> None:
        """Disconnect every connected resource **concurrently**. Idempotent (a signal handler and
        the lifespan ``finally`` may both call it), best-effort, and never raises."""
        if self._closed:
            return
        self._closed = True
        # reverse *registration* order (deterministic; connect order is a race under parallelism),
        # filtered to what actually connected, so nothing half-open or never-opened is disconnected
        targets = [r for r in reversed(self._resources) if r in self._connected]
        await asyncio.gather(*(self._take_down(r) for r in targets))

    async def _take_down(self, resource: Resource) -> None:
        from arvel.kernel.logging import LogManager

        try:
            async with asyncio.timeout(self._shutdown_timeout):
                await resource.disconnect()  # type: ignore[attr-defined]  # in _connected ⇒ ManagedLifecycle
            self._connected.discard(resource)
        except Exception as exc:
            LogManager().channel("resources").error(
                "resource.shutdown.failed", resource=resource.name, error=_err(exc)
            )

    # --- helpers -----------------------------------------------------------
    @staticmethod
    async def _retry(op: Callable[[], Awaitable[_T]], timeout: float, retries: int) -> _T:
        # retries >= 0, so the loop always runs at least once and `last` is always reassigned before
        # the final raise; the placeholder just spares an Optional + assert for the type checker
        last: BaseException = RuntimeError("no attempt made")
        for attempt in range(retries + 1):
            try:
                async with asyncio.timeout(timeout):
                    return await op()
            except Exception as exc:
                last = exc
                if attempt < retries:
                    await asyncio.sleep(min(0.5 * 2**attempt, 2.0))  # capped exponential backoff
        raise last

    def _log_report(self, report: HealthReport) -> None:
        from arvel.kernel.logging import LogManager

        log = LogManager().channel("resources")
        for resource, result in report.entries:
            level = {
                HealthStatus.OK: "info",
                HealthStatus.DEGRADED: "warning",
                HealthStatus.FAILED: "error",
            }[result.status]
            getattr(log, level)(
                "resource.check",
                resource=resource.name,
                status=str(result.status),
                latency_ms=round(result.latency_ms, 1),
                critical=resource.critical,
                detail=result.detail,
            )
        level = "error" if report.critical_failed else ("warning" if report.failed else "info")
        getattr(log, level)(
            "resource.startup",
            ok=report.ok,
            degraded=report.degraded,
            failed=report.failed,
            critical_failed=report.critical_failed,
            decision=report.decision,
        )
