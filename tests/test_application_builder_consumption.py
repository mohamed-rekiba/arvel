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


async def test_with_middlewares_are_exposed_for_the_served_kernel() -> None:
    # The served HttpKernel is built on demand in _build_served_asgi (it is NOT a container
    # singleton — "http" is the HTTP *client*), so builder middlewares are exposed via
    # `app.builder_middlewares` and consumed there, not applied to a boot-time kernel binding.
    # (The end-to-end run of a builder middleware on the served path is covered in
    # test_fluent_bootstrap.test_with_middlewares_loads_a_middleware_file.)
    class Mw: ...

    app = Application.configure().with_middlewares([Mw]).create()
    await app.boot()
    assert list(app.builder_middlewares) == [Mw]


async def test_unconfigured_builder_boots_cleanly() -> None:
    # no with_* calls → no configurators to run, boot must not error
    app = Application.configure().create()
    await app.boot()
    assert app.booted
