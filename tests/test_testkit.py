"""Phase 11 — testkit: facade fakes + client factory."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from arvel.mail import Mailable
from arvel.support.facades import Event, Mail, Queue
from arvel.testing import FakeEvents, FakeMailer, FakeQueue, client, fake, reset_fakes


class WelcomeMail(Mailable):
    def build(self) -> Mailable:
        return self.subject("Welcome")


class OrderPlaced:
    pass


@pytest.fixture(autouse=True)
def _reset() -> Any:
    yield
    reset_fakes()


@pytest.fixture
def booted_app() -> Iterator[Any]:
    from arvel.kernel import Application, set_application

    application = Application()
    set_application(application)
    yield application
    set_application(None)


async def test_mail_fake_records_sends() -> None:
    mailer = fake(Mail)
    assert isinstance(mailer, FakeMailer)
    await Mail.to("ada@example.com").send(WelcomeMail())
    mailer.assert_sent(WelcomeMail)


async def test_queue_fake_records_pushes() -> None:
    queue = fake(Queue)
    assert isinstance(queue, FakeQueue)
    await Queue.push(WelcomeMail, (), {})
    queue.assert_pushed(WelcomeMail)


async def test_events_fake_records_dispatch() -> None:
    events = fake(Event)
    assert isinstance(events, FakeEvents)
    await Event.dispatch(OrderPlaced())
    events.assert_dispatched(OrderPlaced)


def test_assert_nothing_helpers() -> None:
    fake(Mail).assert_nothing_sent()
    fake(Queue).assert_nothing_pushed()


def test_client_factory_serves() -> None:
    from arvel.http import HttpKernel

    kernel = HttpKernel()
    kernel.get("/ping", lambda request: {"ok": True})
    with client(kernel.build()) as http:
        assert http.get("/ping").json() == {"ok": True}


# -- fake_notifications ------------------------------------------------------------------------


async def test_notifications_fake_records_and_asserts(booted_app: Any) -> None:
    from arvel.notifications import Notifiable, Notification
    from arvel.testing import fake_notifications

    class Welcome(Notification):
        pass

    class User(Notifiable):
        pass

    notifications = fake_notifications()
    user = User()
    await user.notify(Welcome())

    notifications.assert_sent_to(user, Welcome)
    notifications.assert_count(1)
    with pytest.raises(AssertionError):
        notifications.assert_nothing_sent()
    with pytest.raises(AssertionError):
        notifications.assert_not_sent_to(user, Welcome)


async def test_notifications_fake_assert_nothing_sent(booted_app: Any) -> None:
    from arvel.notifications import Notification
    from arvel.testing import fake_notifications

    class Welcome(Notification):
        pass

    notifications = fake_notifications()
    notifications.assert_nothing_sent()
    with pytest.raises(AssertionError):
        notifications.assert_sent_to(object(), Welcome)


# -- fake_bus (an alias of fake(Queue) — no duplicate double) -----------------------------------


async def test_bus_fake_is_the_queue_fake() -> None:
    from arvel.testing import fake_bus

    bus = fake_bus()
    assert isinstance(bus, FakeQueue)
    await Queue.push(WelcomeMail, (), {})
    bus.assert_dispatched(WelcomeMail)
    bus.assert_not_dispatched(OrderPlaced)
    with pytest.raises(AssertionError):
        bus.assert_dispatched(OrderPlaced)
    with pytest.raises(AssertionError):
        bus.assert_not_dispatched(WelcomeMail)


async def test_fake_bus_intercepts_bus_chain_and_asserts_the_order(booted_app: Any) -> None:
    """Bus.chain(...).dispatch() resolves the container's `queue` binding directly, bypassing the
    Queue facade — fake_bus() must bind the fake into the container too, not just swap the facade."""
    from arvel.queue import Bus, Job
    from arvel.testing import fake_bus

    class First(Job):
        async def handle(self) -> None:
            pass

    class Second(Job):
        async def handle(self) -> None:
            pass

    bus = fake_bus()
    assert booted_app.make("queue") is bus  # the container binding itself, not just the facade

    await Bus.chain([First(), Second()]).dispatch()

    bus.assert_chained([First, Second])
    with pytest.raises(AssertionError):
        bus.assert_chained([Second, First])


async def test_fake_bus_intercepts_bus_batch_and_asserts_the_group(booted_app: Any) -> None:
    import sqlalchemy as sa

    from arvel.database import ConnectionResolver
    from arvel.queue import Bus, Job
    from arvel.queue.batch import JobBatch
    from arvel.testing import fake_bus

    class Alpha(Job):
        async def handle(self) -> None:
            pass

    class Beta(Job):
        async def handle(self) -> None:
            pass

    db = ConnectionResolver()
    JobBatch.set_connection(db)
    await db.execute(sa.schema.CreateTable(JobBatch.__table__))
    try:
        bus = fake_bus()
        await Bus.batch([Alpha(), Beta()]).dispatch()

        bus.assert_batched(lambda jobs: {type(j) for j in jobs} == {Alpha, Beta})
        with pytest.raises(AssertionError):
            bus.assert_batched(lambda jobs: len(jobs) == 5)
    finally:
        JobBatch.set_connection(None)  # unbind the class-level resolver
        await db.dispose()


# -- fake_http (re-exports Http.fake so arvel.testing is the one surface) -----------------------


async def test_http_fake_via_the_testing_surface(booted_app: Any) -> None:
    from arvel.client import Client
    from arvel.support.facades import Http
    from arvel.testing import fake_http

    booted_app.instance("http", Client())
    http_client = fake_http({"https://api.test/*": Http.response(body={"id": 7})})
    response = await Http.get("https://api.test/x")
    assert response.json() == {"id": 7}
    http_client.assert_sent(lambda r: r.url == "https://api.test/x")

    reset_fakes()
    assert http_client.recorded() == []  # restored — no fake state, so nothing recorded post-reset


# -- response assertions (TestResponse via client()) --------------------------------------------


def test_response_assertion_matrix() -> None:
    import litestar

    from arvel.http import HttpKernel
    from arvel.http.exceptions import HttpException

    class _Invalid(HttpException):
        def __init__(self, errors: dict[str, list[str]]) -> None:
            super().__init__(422, "The given data was invalid.")
            self.errors = errors

    def _reject(request: Any) -> Any:
        raise _Invalid({"name": ["is required"]})

    kernel = HttpKernel()
    kernel.get(
        "/users/1",
        lambda request: {
            "data": {"id": 1, "name": "Ada"},
            "roles": ["admin", "editor"],
            "extra": "ignored",
        },
    )
    kernel.get(
        "/go",
        lambda request: litestar.Response(None, status_code=302, headers={"Location": "/users/1"}),
    )
    kernel.post("/users", _reject)

    with client(kernel.build()) as http:
        (
            http.get("/users/1")
            .assert_ok()
            .assert_json({"data.id": 1})  # subset match — "extra" is tolerated
            .assert_json_path("data.name", "Ada")
            .assert_json_count(2, "roles")
            .assert_json_missing({"nope": 1})
            .assert_see("Ada")
            .assert_header("content-type")
        )

        http.get("/missing").assert_not_found()
        http.get("/go", follow_redirects=False).assert_redirect("/users/1")
        http.post("/users", json={}).assert_unprocessable().assert_json_path(
            "errors.name.0", "is required"
        )

        with pytest.raises(AssertionError):
            http.get("/users/1").assert_status(201)
        with pytest.raises(AssertionError):
            http.get("/users/1").assert_json({"data.id": 999})
        with pytest.raises(AssertionError):
            http.get("/users/1").assert_json_missing({"data.id": 1})
        with pytest.raises(AssertionError):
            http.get("/go", follow_redirects=False).assert_redirect("/nope")


# -- console: cli() --------------------------------------------------------------------------


def test_cli_runs_a_command_class_with_seeded_prompt_and_captured_output() -> None:
    from arvel.console import Command
    from arvel.kernel import Application
    from arvel.testing import cli

    class Greet(Command):
        signature = "greet {name} {--loud}"

        async def handle(self) -> None:
            who = self.ask("who?")
            self.info(f"hello {who} ({self.argument('name')}, loud={self.option('loud')})")

    app = Application()
    app.command_classes.append(Greet)

    result = cli(app, "greet Ada --loud", input=["Bob"])
    result.assert_exit_code(0).assert_output_contains("hello Bob (Ada, loud=True)")


def test_cli_runs_a_console_registered_closure() -> None:
    from arvel.console.closure import ClosureCommand
    from arvel.kernel import Application
    from arvel.testing import cli

    ran: list[str] = []

    async def greet(name: str) -> None:
        ran.append(name)

    app = Application()
    app.console_commands["greet"] = ClosureCommand("greet {name}", greet)

    cli(app, "greet Ada").assert_exit_code(0)
    assert ran == ["Ada"]


def test_cli_assert_exit_code_fails_with_a_readable_message() -> None:
    from arvel.console import Command
    from arvel.kernel import Application
    from arvel.testing import cli

    class Boom(Command):
        signature = "boom"

        async def handle(self) -> None:
            import typer

            raise typer.Exit(1)

    app = Application()
    app.command_classes.append(Boom)

    result = cli(app, "boom")
    result.assert_exit_code(1)
    with pytest.raises(AssertionError, match="expected exit code 0"):
        result.assert_exit_code(0)


def test_cli_unknown_command_raises() -> None:
    from arvel.kernel import Application
    from arvel.testing import cli

    with pytest.raises(ValueError, match="is not registered"):
        cli(Application(), "nope")


def test_cli_positional_default_is_applied_when_omitted() -> None:
    # review MEDIUM: an omitted {name=default} positional must bind its default, matching the CLI
    from arvel.console.closure import ClosureCommand
    from arvel.kernel import Application
    from arvel.testing import cli

    got: list[str] = []

    async def hi(name: str) -> None:
        got.append(name)

    app = Application()
    app.console_commands["hi"] = ClosureCommand("hi {name=World}", hi)
    cli(app, "hi").assert_exit_code(0)  # name omitted -> default "World"
    assert got == ["World"]


def test_assert_json_count_flags_absent_path_and_non_array() -> None:
    # review LOW: count must not silently pass on a missing path or count dict keys
    import pytest

    from arvel.testing import TestResponse

    class _Raw:
        def json(self) -> Any:
            return {"items": [1, 2], "meta": {"a": 1}}

    r = TestResponse(_Raw())  # type: ignore[arg-type]
    r.assert_json_count(2, "items")  # ok
    with pytest.raises(AssertionError, match="absent"):
        r.assert_json_count(0, "nope.path")
    with pytest.raises(AssertionError, match="array"):
        r.assert_json_count(1, "meta")  # a dict, not an array
