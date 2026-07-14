"""Resource lifecycle & health-check manager (DR-0039) — parallel startup, timeout bounding,
abort/degrade decision, partial-startup rollback, and parallel idempotent shutdown."""

from __future__ import annotations

import asyncio
import time

from structlog.testing import capture_logs

from arvel.contracts import HealthResult, HealthStatus
from arvel.kernel.application import Application
from arvel.kernel.resources import ResourceManager, StartupAborted


class FakeResource:
    """A configurable Resource + ManagedLifecycle for exercising the manager."""

    def __init__(
        self,
        name: str,
        *,
        critical: bool = False,
        connect_delay: float = 0.0,
        check_delay: float = 0.0,
        check_status: HealthStatus = HealthStatus.OK,
        fail_check: bool = False,
        fail_disconnect: bool = False,
    ) -> None:
        self.name = name
        self.critical = critical
        self._connect_delay = connect_delay
        self._check_delay = check_delay
        self._check_status = check_status
        self._fail_check = fail_check
        self._fail_disconnect = fail_disconnect
        self.connected = False
        self.disconnected = False

    async def connect(self) -> None:
        await asyncio.sleep(self._connect_delay)
        self.connected = True

    async def disconnect(self) -> None:
        if self._fail_disconnect:
            raise RuntimeError("close failed")
        self.disconnected = True

    async def check(self) -> HealthResult:
        await asyncio.sleep(self._check_delay)
        if self._fail_check:
            raise RuntimeError("boom")
        return HealthResult(self._check_status, detail="ok")


class CheckOnly:
    """A Resource with no lifecycle (not ManagedLifecycle) — the manager must never try to
    connect/disconnect it."""

    def __init__(self, name: str, *, critical: bool = False) -> None:
        self.name = name
        self.critical = critical

    async def check(self) -> HealthResult:
        return HealthResult(HealthStatus.OK)


async def test_startup_runs_connect_and_check_in_parallel() -> None:
    manager = ResourceManager()
    for i in range(4):
        manager.register(FakeResource(f"r{i}", connect_delay=0.15))
    started = time.perf_counter()
    report = await manager.startup()
    elapsed = time.perf_counter() - started
    # 4x0.15s serial would be 0.6s; parallel completes in ~one delay
    assert elapsed < 0.4
    assert report.ok == 4
    assert report.decision == "ready"
    assert all(r.connected for r in manager.resources)  # type: ignore[attr-defined]


async def test_critical_failure_aborts_and_rolls_back() -> None:
    manager = ResourceManager(boot_retries=0)
    good = FakeResource("cache", critical=False)
    bad = FakeResource("db", critical=True, fail_check=True)
    manager.register(good)
    manager.register(bad)
    try:
        await manager.startup()
    except StartupAborted as exc:
        assert exc.report.critical_failed
        assert exc.report.decision == "abort"
    else:
        raise AssertionError("expected StartupAborted")
    # the resource that did connect is disconnected on rollback
    assert good.disconnected


async def test_non_critical_failure_degrades_and_continues() -> None:
    manager = ResourceManager(boot_retries=0)
    manager.register(FakeResource("db", critical=True))
    manager.register(FakeResource("search", critical=False, fail_check=True))
    report = await manager.startup()  # does not raise
    assert report.healthy  # nothing critical failed
    assert report.decision == "degraded"
    assert report.failed == 1


async def test_slow_check_is_bounded_by_timeout() -> None:
    manager = ResourceManager(check_timeout=0.1, boot_retries=0)
    manager.register(FakeResource("slow", check_delay=5.0))
    started = time.perf_counter()
    report = await manager.check_all()
    elapsed = time.perf_counter() - started
    assert elapsed < 0.5  # the 5s check was cut off at 0.1s, not awaited to completion
    assert report.results["slow"].status is HealthStatus.FAILED
    assert report.results["slow"].detail == "timeout"


async def test_shutdown_is_parallel_idempotent_and_never_raises() -> None:
    manager = ResourceManager()
    ok = FakeResource("ok")
    boom = FakeResource("boom", fail_disconnect=True)
    manager.register(ok)
    manager.register(boom)
    await manager.startup()
    await manager.shutdown()  # boom's disconnect raises internally — must be swallowed
    assert ok.disconnected
    await manager.shutdown()  # idempotent second call is a no-op


async def test_shutdown_skips_resources_that_never_connected() -> None:
    manager = ResourceManager(boot_retries=0)
    connected = FakeResource("cache")
    never = FakeResource("db", fail_check=True)  # check fails, but it did connect...
    manager.register(connected)
    # a resource whose *connect* fails must not be disconnected
    failed_connect = FakeResource("broken")

    async def _boom() -> None:
        raise RuntimeError("connect refused")

    failed_connect.connect = _boom  # type: ignore[method-assign]
    manager.register(failed_connect)
    manager.register(never)
    await manager.startup()
    await manager.shutdown()
    assert connected.disconnected
    assert not failed_connect.disconnected  # never connected → never disconnected


async def test_check_only_resource_is_never_connected_or_disconnected() -> None:
    manager = ResourceManager()
    resource = CheckOnly("stateless")
    manager.register(resource)
    report = await manager.startup()
    assert report.ok == 1
    await manager.shutdown()  # must not raise trying to call a missing disconnect


async def test_aggregate_status_is_worst_case() -> None:
    manager = ResourceManager(boot_retries=0)
    manager.register(FakeResource("a", check_status=HealthStatus.OK))
    manager.register(FakeResource("b", check_status=HealthStatus.DEGRADED))
    report = await manager.check_all()
    assert report.status is HealthStatus.DEGRADED  # OK + DEGRADED → DEGRADED
    manager.register(FakeResource("c", fail_check=True))
    report = await manager.check_all()
    assert report.status is HealthStatus.FAILED  # + FAILED → FAILED


async def test_register_dedupes_by_name() -> None:
    manager = ResourceManager()
    manager.register(FakeResource("db", critical=False))
    manager.register(FakeResource("db", critical=True))
    assert len(manager.resources) == 1
    assert manager.resources[0].critical is True  # the later registration wins


async def test_startup_emits_structured_report() -> None:
    manager = ResourceManager()
    manager.register(FakeResource("db", critical=True))
    with capture_logs() as logs:
        await manager.startup()
    events = {log["event"] for log in logs}
    assert "resource.check" in events
    assert "resource.startup" in events
    startup = next(log for log in logs if log["event"] == "resource.startup")
    assert startup["decision"] == "ready"
    assert startup["ok"] == 1


async def test_application_boot_starts_and_terminate_shuts_down_resources() -> None:
    app = Application()
    resource = FakeResource("fake")
    app.resources.register(resource)
    await app.boot()
    assert resource.connected  # startup ran during boot
    await app.terminate()
    assert resource.disconnected  # shutdown ran during terminate


async def test_startup_retries_a_transient_check_failure() -> None:
    """A check that fails once then succeeds within boot_retries is retried, not failed — locks the
    _retry backoff loop."""
    attempts = {"n": 0}

    class Flaky:
        name = "flaky"
        critical = False

        async def check(self) -> HealthResult:
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("transient")
            return HealthResult(HealthStatus.OK, detail="recovered")

    manager = ResourceManager(boot_retries=1)
    manager.register(Flaky())
    report = await manager.startup()
    assert attempts["n"] == 2  # failed once, retried once, then succeeded
    assert report.results["flaky"].status is HealthStatus.OK
    assert report.ok == 1


async def test_health_endpoint_withholds_failure_detail_unless_debug() -> None:
    """The /health body must not leak a failed resource's raw exception string (internal
    hostnames/ports) to an unauthenticated caller in production — only under app.debug."""
    from arvel.http.health import health
    from arvel.kernel import set_application

    class Down:
        name = "cache"
        critical = False

        async def check(self) -> HealthResult:
            raise RuntimeError("Error 111 connecting to redis-host:6379")

    async def detail_for(debug: bool) -> str | None:
        app = Application()
        app.make("config").set("app.debug", debug)
        set_application(app)
        try:
            app.resources.register(Down())
            resp = await health()
            return resp.content.resources["cache"].detail
        finally:
            set_application(None)

    assert await detail_for(False) is None  # production: withheld
    shown = await detail_for(True)
    assert shown is not None and "redis-host" in shown  # debug: shown for local diagnosis
