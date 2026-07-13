"""Integration: the SERVED ASGI app boots arvel via its real lifespan — as_asgi() + TestClient runs
bootstrap_app (sync) and boot()/terminate() (async), the production path unit tests miss."""

from __future__ import annotations

from pathlib import Path

import pytest

from arvel.kernel import Application, set_application
from arvel.kernel.service_provider import ServiceProvider


def test_served_app_boots_and_terminates_via_lifespan() -> None:
    from litestar.testing import TestClient

    flags: dict[str, bool] = {}

    class FlagProvider(ServiceProvider):
        def register(self) -> None:
            self.app.terminating(lambda: flags.__setitem__("terminated", True))

        async def boot(self) -> None:
            flags["booted"] = True

    app = Application()
    app.app_provider_classes.append(FlagProvider)  # discovered + registered by bootstrap_app
    try:
        asgi = app.as_asgi()  # sync bootstrap ran (providers registered) but NOT booted yet
        assert app.booted is False

        with TestClient(app=asgi):  # entering runs the ASGI lifespan → boot()
            assert app.booted is True
            assert flags.get("booted") is True
        assert flags.get("terminated") is True  # shutdown ran terminate()
    finally:
        set_application(None)


def test_boot_failure_runs_terminate_and_propagates() -> None:
    from litestar.testing import TestClient

    flags: dict[str, bool] = {}

    class BadProvider(ServiceProvider):
        def register(self) -> None:
            self.app.terminating(lambda: flags.__setitem__("terminated", True))

        async def boot(self) -> None:
            raise RuntimeError("boom during boot")

    app = Application()
    app.app_provider_classes.append(BadProvider)
    try:
        asgi = app.as_asgi()
        # the TaskGroup wraps the startup failure in an ExceptionGroup; _exception_messages unwraps it
        with pytest.raises(BaseException) as exc_info, TestClient(app=asgi):
            pass
        assert any("boom during boot" in m for m in _exception_messages(exc_info.value))
        assert flags.get("terminated") is True  # a failed boot still cleans up via terminate()
    finally:
        set_application(None)


def test_recorded_route_files_are_imported_and_served(tmp_path: Path) -> None:
    # a route file recorded via load_routes_from/with_routing must be IMPORTED at boot so its
    # Route.* defs register into the router.
    from litestar.testing import TestClient

    (tmp_path / "web.py").write_text(
        "from arvel import Route\n\nRoute.get('/ping', lambda request: {'pong': True})\n"
    )
    app = Application(base_path=str(tmp_path))
    app.route_files.append("web.py")  # as load_routes_from() / with_routing() would record it
    try:
        asgi = app.as_asgi()
        with TestClient(app=asgi) as client:
            assert client.get("/ping").json() == {"pong": True}
    finally:
        set_application(None)


def test_duplicate_route_file_entries_are_imported_once(tmp_path: Path) -> None:
    # the same file recorded under different spellings must import once, else Litestar
    # raises on the duplicate route.
    from litestar.testing import TestClient

    (tmp_path / "web.py").write_text(
        "from arvel import Route\n\nRoute.get('/ping', lambda request: {'pong': True})\n"
    )
    app = Application(base_path=str(tmp_path))
    app.route_files.extend(["web.py", "sub/../web.py"])  # two spellings of the same file
    try:
        asgi = app.as_asgi()  # must not raise a duplicate-route error
        with TestClient(app=asgi) as client:
            assert client.get("/ping").json() == {"pong": True}
    finally:
        set_application(None)


def test_missing_route_file_is_skipped_with_warning(tmp_path: Path) -> None:
    from structlog.testing import capture_logs

    from arvel.kernel.bootstrap import load_route_files

    # load_route_files directly — as_asgi() re-runs configure_logging and would clobber capture_logs.
    app = Application(base_path=str(tmp_path))
    app.route_files.append("does_not_exist.py")
    with capture_logs() as logs:
        load_route_files(app)
    assert any(
        log.get("event") == "route_file_not_found" and log.get("path") == "does_not_exist.py"
        for log in logs
    )


def test_bootstrap_app_is_idempotent() -> None:
    # calling as_asgi() twice must be a no-op (the bootstrapped guard).
    app = Application()
    try:
        app.as_asgi()
        assert app.bootstrapped is True
        providers = len(app.registered_provider_types)
        app.as_asgi()  # second call → short-circuits on app.bootstrapped
        assert len(app.registered_provider_types) == providers  # no re-discovery
    finally:
        set_application(None)


def _exception_messages(exc: BaseException) -> list[str]:
    messages = [str(exc)]
    for sub in getattr(exc, "exceptions", ()):  # unwrap ExceptionGroup
        messages.extend(_exception_messages(sub))
    if exc.__cause__ is not None:
        messages.extend(_exception_messages(exc.__cause__))
    return messages
