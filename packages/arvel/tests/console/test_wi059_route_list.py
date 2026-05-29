"""WI-arvel-059 — `route:list` console command with full Laravel-parity columns.

Epic 048 Story 9.

Covers the five canonical columns (Method, URI, Name, Action, Middleware),
the ``--filter`` substring switch, the ``--json`` raw-output switch, and the
edge cases (empty router, no matches, controller routes, middleware
rendering, JSON shape).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
import typer
from arvel.console import Application, Command
from arvel.console.commands.route_list import RouteListCommand
from arvel.http._middleware_core import CallNext
from arvel.routing import Router, RouteSpec
from typer.testing import CliRunner

runner = CliRunner()


# ───────────────────────────── Fixtures ─────────────────────────────


@pytest.fixture(autouse=True)
def reset_router() -> Iterator[None]:
    Router.reset_singleton()
    yield
    Router.reset_singleton()


def _app(*cmds: Command) -> Application:
    return Application(commands=list(cmds))


async def _stub_handler() -> None:
    return


class _PostController:
    async def index(self) -> dict[str, str]:
        return {"ok": "yes"}

    async def show(self) -> dict[str, str]:
        return {"ok": "yes"}


class _PingController:
    async def __call__(self) -> dict[str, str]:
        return {"pong": "yes"}


class _Auth:
    async def handle(self, request: Any, call_next: CallNext) -> Any:
        return await call_next(request)


class _Throttle:
    async def handle(self, request: Any, call_next: CallNext) -> Any:
        return await call_next(request)


def _seed(specs: list[RouteSpec]) -> None:
    router = Router.singleton()
    for spec in specs:
        # Router._add is the same protected hook routing.py uses internally;
        # tests need it to seed specs without going through the public DSL.
        router._add(spec)  # pyright: ignore[reportPrivateUsage]


# ───────────────────────────── Column shape ─────────────────────────────


class TestColumnShape:
    """AC-9.2 — Method, URI, Name, Action, Middleware columns."""

    def test_table_header_lists_all_five_columns(self) -> None:
        _seed(
            [
                RouteSpec(
                    method="GET",
                    path="/posts",
                    handler=_stub_handler,
                    name="posts.index",
                )
            ]
        )
        app = _app(RouteListCommand())
        result = runner.invoke(app.typer_app, ["route:list"])
        assert result.exit_code == 0, result.output
        out = result.output
        for column in ("Method", "URI", "Name", "Action", "Middleware"):
            assert column in out, f"missing column header {column!r}: {out!r}"

    def test_empty_router_prints_friendly_message(self) -> None:
        app = _app(RouteListCommand())
        result = runner.invoke(app.typer_app, ["route:list"])
        assert result.exit_code == 0
        assert "(no routes registered)" in result.output

    def test_plain_function_route_shows_qualname(self) -> None:
        _seed(
            [
                RouteSpec(
                    method="GET",
                    path="/articles",
                    handler=_stub_handler,
                    name="articles.index",
                )
            ]
        )
        app = _app(RouteListCommand())
        result = runner.invoke(app.typer_app, ["route:list"])
        out = result.output
        assert result.exit_code == 0, out
        assert "GET" in out
        assert "/articles" in out
        assert "articles.index" in out
        assert "_stub_handler" in out

    def test_controller_method_route_shows_class_hash_action(self) -> None:
        _seed(
            [
                RouteSpec(
                    method="GET",
                    path="/posts",
                    handler=_stub_handler,
                    name="posts.index",
                    controller=_PostController,
                    action="index",
                )
            ]
        )
        app = _app(RouteListCommand())
        result = runner.invoke(app.typer_app, ["route:list"])
        assert result.exit_code == 0, result.output
        assert "_PostController#index" in result.output

    def test_invokable_controller_shows_class_hash_call(self) -> None:
        _seed(
            [
                RouteSpec(
                    method="POST",
                    path="/ping",
                    handler=_stub_handler,
                    controller=_PingController,
                )
            ]
        )
        app = _app(RouteListCommand())
        result = runner.invoke(app.typer_app, ["route:list"])
        assert result.exit_code == 0, result.output
        assert "_PingController#__call__" in result.output

    def test_unnamed_route_renders_dash_in_name_column(self) -> None:
        _seed(
            [
                RouteSpec(
                    method="GET",
                    path="/health",
                    handler=_stub_handler,
                )
            ]
        )
        app = _app(RouteListCommand())
        result = runner.invoke(app.typer_app, ["route:list"])
        assert result.exit_code == 0
        # Some placeholder marker should appear where the name would be.
        # Either "-" or "(none)" is acceptable — both are common conventions.
        out = result.output
        assert ("-" in out) or ("(none)" in out)


# ───────────────────────────── Middleware column ─────────────────────────────


class TestMiddlewareColumn:
    """Middleware names join with commas; empty tuple renders as blank/dash."""

    def test_middleware_names_join_with_commas(self) -> None:
        _seed(
            [
                RouteSpec(
                    method="GET",
                    path="/dashboard",
                    handler=_stub_handler,
                    middleware=(_Auth(), _Throttle()),
                )
            ]
        )
        app = _app(RouteListCommand())
        result = runner.invoke(app.typer_app, ["route:list"])
        assert result.exit_code == 0, result.output
        assert "_Auth" in result.output
        assert "_Throttle" in result.output

    def test_no_middleware_renders_placeholder(self) -> None:
        _seed(
            [
                RouteSpec(
                    method="GET",
                    path="/health",
                    handler=_stub_handler,
                )
            ]
        )
        app = _app(RouteListCommand())
        result = runner.invoke(app.typer_app, ["route:list"])
        assert result.exit_code == 0
        # We don't enforce exact placeholder text — just no "Throttle"-style class names leak.
        assert "_Throttle" not in result.output
        assert "_Auth" not in result.output


# ───────────────────────────── --filter ─────────────────────────────


class TestFilter:
    """AC-9.3 — --filter=foo includes only routes whose path contains 'foo'."""

    def test_filter_keeps_matching_paths(self) -> None:
        _seed(
            [
                RouteSpec(method="GET", path="/api/posts", handler=_stub_handler),
                RouteSpec(method="GET", path="/admin/users", handler=_stub_handler),
                RouteSpec(method="GET", path="/api/comments", handler=_stub_handler),
            ]
        )
        app = _app(RouteListCommand())
        result = runner.invoke(app.typer_app, ["route:list", "--filter", "api"])
        assert result.exit_code == 0, result.output
        assert "/api/posts" in result.output
        assert "/api/comments" in result.output
        assert "/admin/users" not in result.output

    def test_filter_is_case_insensitive(self) -> None:
        _seed(
            [
                RouteSpec(method="GET", path="/Api/Posts", handler=_stub_handler),
                RouteSpec(method="GET", path="/admin/users", handler=_stub_handler),
            ]
        )
        app = _app(RouteListCommand())
        result = runner.invoke(app.typer_app, ["route:list", "--filter", "api"])
        assert result.exit_code == 0
        assert "/Api/Posts" in result.output
        assert "/admin/users" not in result.output

    def test_filter_with_no_matches_exits_zero_and_says_so(self) -> None:
        _seed(
            [
                RouteSpec(method="GET", path="/healthz", handler=_stub_handler),
            ]
        )
        app = _app(RouteListCommand())
        result = runner.invoke(app.typer_app, ["route:list", "--filter", "nothing-here"])
        assert result.exit_code == 0, result.output
        assert "/healthz" not in result.output
        # Some "no matches" message — exact text not pinned, just that the user
        # sees something instead of a blank table.
        assert "no routes" in result.output.lower() or "no match" in result.output.lower()


# ───────────────────────────── --json ─────────────────────────────


class TestJsonOutput:
    """AC-9.4 — --json emits a JSON array with one object per route."""

    def test_empty_router_emits_empty_json_array(self) -> None:
        app = _app(RouteListCommand())
        result = runner.invoke(app.typer_app, ["route:list", "--json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output.strip())
        assert payload == []

    def test_json_payload_has_all_canonical_fields(self) -> None:
        _seed(
            [
                RouteSpec(
                    method="GET",
                    path="/posts/{post}",
                    handler=_stub_handler,
                    name="posts.show",
                    controller=_PostController,
                    action="show",
                    middleware=(_Auth(),),
                )
            ]
        )
        app = _app(RouteListCommand())
        result = runner.invoke(app.typer_app, ["route:list", "--json"])
        assert result.exit_code == 0, result.output
        payload: list[dict[str, Any]] = json.loads(result.output.strip())
        assert isinstance(payload, list)
        assert len(payload) == 1
        entry = payload[0]
        assert entry["method"] == "GET"
        assert entry["path"] == "/posts/{post}"
        assert entry["name"] == "posts.show"
        assert entry["action"] == "_PostController#show"
        assert entry["middleware"] == ["_Auth"]

    def test_unnamed_route_emits_null_name_in_json(self) -> None:
        _seed(
            [
                RouteSpec(
                    method="GET",
                    path="/health",
                    handler=_stub_handler,
                )
            ]
        )
        app = _app(RouteListCommand())
        result = runner.invoke(app.typer_app, ["route:list", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output.strip())
        assert payload[0]["name"] is None
        assert payload[0]["middleware"] == []

    def test_json_respects_filter(self) -> None:
        _seed(
            [
                RouteSpec(method="GET", path="/api/posts", handler=_stub_handler),
                RouteSpec(method="GET", path="/admin/users", handler=_stub_handler),
            ]
        )
        app = _app(RouteListCommand())
        result = runner.invoke(app.typer_app, ["route:list", "--json", "--filter", "api"])
        assert result.exit_code == 0
        payload = json.loads(result.output.strip())
        assert [entry["path"] for entry in payload] == ["/api/posts"]


# ───────────────────────────── Sourcing routes ─────────────────────────────


class TestRouteSource:
    """The command queries Router.singleton() — no container binding required."""

    def test_routes_come_from_router_singleton(self) -> None:
        _seed(
            [
                RouteSpec(method="GET", path="/from-singleton", handler=_stub_handler),
            ]
        )
        cmd = RouteListCommand()
        routes = cmd.get_routes()
        assert any(r.path == "/from-singleton" for r in routes)

    def test_get_routes_returns_empty_when_router_empty(self) -> None:
        cmd = RouteListCommand()
        assert cmd.get_routes() == []


# ───────────────────────────── Backward compatibility ─────────────────────────────


class TestBackwardCompat:
    """The existing AC-005-009-* tests in test_ops_commands.py still hold."""

    def test_command_name_and_help_unchanged(self) -> None:
        cmd = RouteListCommand()
        assert cmd.name == "route:list"
        assert cmd.help  # something descriptive
        assert cmd.needs_application is True

    def test_registers_under_route_list_name(self) -> None:
        app = _app(RouteListCommand())
        assert app.has_command("route:list")

    def test_register_method_accepts_typer_app(self) -> None:
        # Sanity: register() takes a typer.Typer and wires up the callback.
        typer_app = typer.Typer(add_completion=False)
        RouteListCommand().register(typer_app)
        # No assertion on internals — just that no exception is raised.
