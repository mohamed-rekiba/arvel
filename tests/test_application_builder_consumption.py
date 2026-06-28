"""Kernel (doc 03) — ApplicationBuilder.with_routing/middleware/exceptions are actually
consumed, not silently dropped (C2). Test-first."""

from __future__ import annotations

from arvel.kernel.application import Application


def test_with_routing_populates_route_registries() -> None:
    builder = Application.configure()
    builder.with_routing(web="routes/web.py", api="routes/api.py")
    app = builder.create()
    # the group→file map is preserved AND the files land in the route registry boot reads
    assert app.routing == {"web": "routes/web.py", "api": "routes/api.py"}
    assert "routes/web.py" in app.route_files
    assert "routes/api.py" in app.route_files


async def test_with_exceptions_configures_the_bound_handler_at_boot() -> None:
    builder = Application.configure()
    received: list[object] = []
    builder.with_exceptions(lambda handler: received.append(handler))
    app = builder.create()
    sentinel = object()
    app.instance("exceptions", sentinel)
    await app.boot()
    assert received == [sentinel]  # configure callback ran against the bound handler


async def test_with_middlewares_appends_to_the_kernel_global_stack_at_boot() -> None:
    builder = Application.configure()

    class Mw: ...

    builder.with_middlewares([Mw])
    app = builder.create()

    class Kernel:
        def __init__(self) -> None:
            self.global_middleware: list[object] = []

        def resolve_middleware(self, ref: object) -> object:
            return ref

    kernel = Kernel()
    app.instance("http", kernel)
    await app.boot()
    assert kernel.global_middleware == [Mw]  # the builder's middleware landed on the global stack


async def test_unconfigured_builder_boots_cleanly() -> None:
    # no with_* calls → no configurators to run, boot must not error
    app = Application.configure().create()
    await app.boot()
    assert app.booted
