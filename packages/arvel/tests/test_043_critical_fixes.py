"""Failing tests for C-001 through C-004.

All four tests must be RED before implementation begins.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest
from pydantic import BaseModel

# C-001: SyntaxError in SchedulerKernel


class TestC001SchedulerImport:
    """C-001: scheduler must import and run cleanly under Python 3.

    Python 3.14 accepts `except E1, attr.E2:` as a tuple-catch, so this is a
    style fix (add parens) not a runtime crash. Tests verify the behaviour is correct.
    """

    def test_scheduler_kernel_can_be_imported(self) -> None:
        """SchedulerKernel must import cleanly under Python 3."""
        from arvel.scheduling.kernel import SchedulerKernel

        assert SchedulerKernel is not None

    def test_scheduler_kernel_interrupt_handler_uses_tuple_except(self) -> None:
        """The interrupt handler must use the explicit Python 3 tuple form."""
        from arvel.scheduling.kernel import SchedulerKernel

        source = inspect.getsource(SchedulerKernel.serve_forever)
        assert "except (" in source
        assert "KeyboardInterrupt" in source
        assert "asyncio.CancelledError" in source

    @pytest.mark.asyncio
    async def test_scheduler_kernel_serve_forever_runs_max_iterations(self) -> None:
        """serve_forever(max_iterations=1) must complete without error."""
        from arvel.scheduling import Schedule, SchedulerKernel

        schedule = Schedule()
        kernel = SchedulerKernel(schedule=schedule)
        await kernel.serve_forever(sleep_seconds=0, max_iterations=1)


# C-002: Controller DI bypass


class TestC002ControllerDI:
    """C-002: Invokable controllers must be resolved through the container."""

    def test_invokable_controller_with_dependency_gets_injected(self) -> None:
        """Container must supply constructor dependencies when mounting a route."""
        from arvel.container import Container
        from arvel.http.controller import Controller
        from arvel.routing import Route, Router
        from fastapi import FastAPI
        from starlette.testclient import TestClient

        Router.reset_singleton()

        class GreetService:
            def greet(self) -> str:
                return "hello from service"

        class MyController(Controller):
            def __init__(self, svc: GreetService) -> None:
                self.svc = svc

            async def __call__(self) -> dict[str, str]:
                return {"msg": self.svc.greet()}

        Route.get("/greet", controller=MyController)

        app = FastAPI()
        container = Container()
        container.bind(GreetService)
        app.state.arvel_container = container
        Router.singleton().register_with_app(app)

        resp = TestClient(app).get("/greet")
        assert resp.status_code == 200
        assert resp.json() == {"msg": "hello from service"}

    def test_invokable_controller_without_dependency_still_works(self) -> None:
        """No regression: zero-arg controllers must continue to work."""
        from arvel.http.controller import Controller
        from arvel.routing import Route, Router
        from fastapi import FastAPI
        from starlette.testclient import TestClient

        Router.reset_singleton()

        class PingController(Controller):
            async def __call__(self) -> dict[str, str]:
                return {"ping": "pong"}

        Route.get("/ping", controller=PingController)

        app = FastAPI()
        Router.singleton().register_with_app(app)

        resp = TestClient(app).get("/ping")
        assert resp.status_code == 200
        assert resp.json() == {"ping": "pong"}

    def test_invokable_controller_unbound_dependency_raises_resolution_error(self) -> None:
        """Container failures must stay DI errors, not constructor TypeErrors."""
        from arvel.container import BindingResolutionError, Container
        from arvel.http.controller import Controller
        from arvel.routing import Route, Router
        from fastapi import FastAPI

        Router.reset_singleton()

        class MissingService:
            pass

        class BrokenController(Controller):
            def __init__(self, svc: MissingService) -> None:
                self.svc = svc

            async def __call__(self) -> dict[str, str]:  # pragma: no cover
                return {"msg": "unreachable"}

        Route.get("/broken", controller=BrokenController)

        app = FastAPI()
        app.state.arvel_container = Container()
        with pytest.raises(BindingResolutionError):
            Router.singleton().register_with_app(app)


# C-003: Listener DI bypass


class TestC003ListenerDI:
    """C-003: Event listeners must be resolved through the container."""

    @pytest.mark.asyncio
    async def test_listener_with_dependency_gets_injected(self) -> None:
        """Container must supply constructor dependencies when dispatching an event."""
        from arvel.container import Container
        from arvel.events.dispatcher import EventDispatcher
        from arvel.events.event import Event
        from arvel.events.listener import Listener

        class FakeMailer:
            def __init__(self) -> None:
                self.sent: list[str] = []

            def send(self, msg: str) -> None:
                self.sent.append(msg)

        class UserRegistered(Event):
            email: str

        class WelcomeEmailListener(Listener[UserRegistered]):
            def __init__(self, mailer: FakeMailer) -> None:
                self.mailer = mailer

            async def handle(self, event: UserRegistered) -> None:
                self.mailer.send(event.email)

        mailer = FakeMailer()
        container = Container()
        container.instance(FakeMailer, mailer)

        dispatcher = EventDispatcher(container=container)
        dispatcher.listen(UserRegistered, WelcomeEmailListener)
        await dispatcher.dispatch(UserRegistered(email="alice@example.com"))

        assert mailer.sent == ["alice@example.com"]

    @pytest.mark.asyncio
    async def test_listener_without_dependency_still_works(self) -> None:
        """No regression: zero-arg listeners must work without a container."""
        from arvel.events.dispatcher import EventDispatcher
        from arvel.events.event import Event
        from arvel.events.listener import Listener

        handled: list[str] = []

        class PingEvent(Event):
            msg: str

        class PingListener(Listener[PingEvent]):
            async def handle(self, event: PingEvent) -> None:
                handled.append(event.msg)

        dispatcher = EventDispatcher()
        dispatcher.listen(PingEvent, PingListener)
        await dispatcher.dispatch(PingEvent(msg="hello"))

        assert handled == ["hello"]

    @pytest.mark.asyncio
    async def test_listener_di_error_is_caught_fault_isolated(self) -> None:
        """DI resolution errors must be caught; subsequent listeners still run."""
        from arvel.events.dispatcher import EventDispatcher
        from arvel.events.event import Event
        from arvel.events.listener import Listener

        ran: list[str] = []

        class BoomError(Exception):
            pass

        class MyEvent(Event):
            pass

        class FailingListener(Listener[MyEvent]):
            def __init__(self) -> None:
                raise BoomError("constructor fails")

            async def handle(self, event: MyEvent) -> None:  # pragma: no cover
                pass

        class GoodListener(Listener[MyEvent]):
            async def handle(self, event: MyEvent) -> None:
                ran.append("good")

        dispatcher = EventDispatcher()
        dispatcher.listen(MyEvent, FailingListener)
        dispatcher.listen(MyEvent, GoodListener)
        await dispatcher.dispatch(MyEvent())

        assert ran == ["good"]


# C-004: FormRequest.authorize() default


class _Payload(BaseModel):
    x: int


class TestC004AuthorizeDefault:
    """C-004: FormRequest.authorize() must deny by default (OWASP A01)."""

    @pytest.mark.asyncio
    async def test_authorize_default_returns_false(self) -> None:
        """Base FormRequest.authorize() must return False, not True."""
        from arvel.http.requests import FormRequest

        form: FormRequest[_Payload] = FormRequest(_Payload(x=1))
        result = await form.authorize(object())
        assert result is False

    def test_form_request_with_no_authorize_override_returns_403(self) -> None:
        """Route with an unoverridden FormRequest must respond 403 for valid input."""
        from arvel.http.exceptions import HttpExceptionHandler
        from arvel.http.requests import FormRequest
        from arvel.routing import Route, Router
        from fastapi import FastAPI
        from starlette.testclient import TestClient

        Router.reset_singleton()

        class StrictRequest(FormRequest[_Payload]):
            pass  # no authorize override — should deny

        @Route.post("/strict")
        async def endpoint(form: StrictRequest) -> dict[str, Any]:  # pragma: no cover
            return {"ok": True}

        del endpoint
        app = FastAPI()
        HttpExceptionHandler().register(app)
        Router.singleton().register_with_app(app)

        resp = TestClient(app).post("/strict", json={"x": 42})
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "FORBIDDEN"

    def test_authorize_can_be_overridden_to_allow(self) -> None:
        """An explicit return True override must still permit the request."""
        from arvel.http.exceptions import HttpExceptionHandler
        from arvel.http.requests import FormRequest
        from arvel.routing import Route, Router
        from fastapi import FastAPI
        from starlette.testclient import TestClient

        Router.reset_singleton()

        class AllowedRequest(FormRequest[_Payload]):
            async def authorize(self, request: Any) -> bool:
                return True

        @Route.post("/allowed")
        async def endpoint(form: AllowedRequest) -> dict[str, Any]:
            return {"ok": True, "x": form.validated().x}

        del endpoint
        app = FastAPI()
        HttpExceptionHandler().register(app)
        Router.singleton().register_with_app(app)

        resp = TestClient(app).post("/allowed", json={"x": 42})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "x": 42}
