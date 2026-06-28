"""Phase D / It.6 — lifecycle correctness: LIFO terminate (T1), warn on dropped async deferred boot
(B2), late-provider translation finalization (B3), register-after-boot boots the provider (B8)."""

from __future__ import annotations

from structlog.testing import capture_logs

from arvel.kernel import ServiceProvider, set_application
from arvel.kernel.application import Application


async def test_terminate_runs_callbacks_lifo() -> None:
    app = Application()
    order: list[str] = []
    app.terminating(lambda: order.append("first"))
    app.terminating(lambda: order.append("second"))
    await app.terminate()
    assert order == ["second", "first"]  # T1: reverse of registration order


async def test_register_after_boot_boots_the_provider() -> None:
    app = Application()
    set_application(app)
    await app.boot()
    booted: list[bool] = []

    class LateProvider(ServiceProvider):
        def register(self) -> None: ...
        def boot(self) -> None:
            booted.append(True)

    try:
        app.register(LateProvider(app))
        assert booted == [True]  # B8: boot ran despite registering after the boot loop
    finally:
        set_application(None)


async def test_post_boot_async_boot_warns() -> None:
    app = Application()
    set_application(app)
    await app.boot()

    class AsyncLate(ServiceProvider):
        def register(self) -> None: ...
        async def boot(self) -> None: ...  # async boot triggered after startup → skipped + warned

    try:
        with capture_logs() as logs:
            app.register(AsyncLate(app))
        assert any(log.get("event") == "async_deferred_boot_skipped" for log in logs)  # B2
    finally:
        set_application(None)


async def test_post_boot_provider_translations_reach_the_translator() -> None:
    app = Application()
    set_application(app)
    applied: list[tuple[str, str]] = []

    class FakeTranslator:
        def add_namespace(self, namespace: str, path: str) -> None:
            applied.append((namespace, path))

    app.instance("translator", FakeTranslator())
    await app.boot()

    class PkgProvider(ServiceProvider):
        def register(self) -> None:
            self.load_translations_from("/pkg/lang", "pkg")

        def boot(self) -> None: ...

    try:
        app.register(PkgProvider(app))
        assert ("pkg", "/pkg/lang") in applied  # B3: late namespace reached the translator
    finally:
        set_application(None)
