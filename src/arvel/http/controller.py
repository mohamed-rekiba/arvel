"""Controller DI bridge — connects FastAPI Depends() to the Arvel container.

Controllers are resolved from the request-scoped container with all
constructor dependencies injected. FastAPI handles path/query/body params.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypeVar, cast

from fastapi import Depends, Request  # noqa: TC002

if TYPE_CHECKING:
    from collections.abc import Callable

    from arvel.foundation.container import Container

T = TypeVar("T")
F = TypeVar("F", bound="Callable[..., object]")


@dataclass(frozen=True)
class ControllerRouteMeta:
    """Metadata attached by ``route`` decorators on controller methods."""

    method: str
    path: str
    name: str | None = None
    middleware: list[str] = field(default_factory=list)
    without_middleware: list[str] = field(default_factory=list)
    fastapi_kwargs: dict[str, object] = field(default_factory=dict)


class _RouteDecoratorFactory:
    """Build decorators that attach route metadata to controller methods."""

    def _register(
        self,
        method: str,
        path: str,
        *,
        name: str | None = None,
        middleware: list[str] | None = None,
        without_middleware: list[str] | None = None,
        **fastapi_kwargs: object,
    ) -> Callable[[F], F]:
        if "methods" in fastapi_kwargs:
            raise ValueError(
                "Do not pass 'methods' to route decorators; it is set by @route.<verb>."
            )

        def decorator(fn: F) -> F:
            fn.__arvel_controller_route__ = ControllerRouteMeta(
                method=method,
                path=path,
                name=name,
                middleware=list(middleware or []),
                without_middleware=list(without_middleware or []),
                fastapi_kwargs=dict(fastapi_kwargs),
            )
            return fn

        return decorator

    def get(
        self,
        path: str,
        *,
        name: str | None = None,
        middleware: list[str] | None = None,
        without_middleware: list[str] | None = None,
        **fastapi_kwargs: object,
    ) -> Callable[[F], F]:
        return self._register(
            "GET",
            path,
            name=name,
            middleware=middleware,
            without_middleware=without_middleware,
            **fastapi_kwargs,
        )

    def post(
        self,
        path: str,
        *,
        name: str | None = None,
        middleware: list[str] | None = None,
        without_middleware: list[str] | None = None,
        **fastapi_kwargs: object,
    ) -> Callable[[F], F]:
        return self._register(
            "POST",
            path,
            name=name,
            middleware=middleware,
            without_middleware=without_middleware,
            **fastapi_kwargs,
        )

    def put(
        self,
        path: str,
        *,
        name: str | None = None,
        middleware: list[str] | None = None,
        without_middleware: list[str] | None = None,
        **fastapi_kwargs: object,
    ) -> Callable[[F], F]:
        return self._register(
            "PUT",
            path,
            name=name,
            middleware=middleware,
            without_middleware=without_middleware,
            **fastapi_kwargs,
        )

    def patch(
        self,
        path: str,
        *,
        name: str | None = None,
        middleware: list[str] | None = None,
        without_middleware: list[str] | None = None,
        **fastapi_kwargs: object,
    ) -> Callable[[F], F]:
        return self._register(
            "PATCH",
            path,
            name=name,
            middleware=middleware,
            without_middleware=without_middleware,
            **fastapi_kwargs,
        )

    def delete(
        self,
        path: str,
        *,
        name: str | None = None,
        middleware: list[str] | None = None,
        without_middleware: list[str] | None = None,
        **fastapi_kwargs: object,
    ) -> Callable[[F], F]:
        return self._register(
            "DELETE",
            path,
            name=name,
            middleware=middleware,
            without_middleware=without_middleware,
            **fastapi_kwargs,
        )


route = _RouteDecoratorFactory()


class BaseController:
    """Base class for declarative class-based route controllers."""

    prefix: str = ""
    tags: tuple[str, ...] = ()
    description: str | None = None
    middleware: tuple[str, ...] = ()


def get_request_container(request: Request) -> Container:
    """Extract the request-scoped Arvel container from the ASGI state."""
    container = getattr(request.state, "container", None)
    if container is None:
        raise RuntimeError(
            "No request-scoped container found. Is RequestContainerMiddleware installed?"
        )
    return container


def Inject[T](interface: type[T]) -> T:  # noqa: N802
    """Declare a controller parameter resolved from the Arvel DI container.

    Use as a default value in controller method signatures::

        async def login(
            self,
            payload: LoginRequest,
            token_service: TokenService = Inject(TokenService),
            hasher: HasherContract = Inject(HasherContract),
        ) -> TokenResponse:
            ...

    At request time, ``RequestContainerMiddleware`` stores a request-scoped
    child container in ``request.state.container``.  FastAPI treats
    ``Inject(T)`` as a ``Depends()`` and calls the inner resolver, which
    pulls ``T`` from that container.

    The return type is ``T`` (not ``Depends``) so type checkers see the
    correct type inside the method body.
    """

    async def _resolver(request: Request) -> T:
        container = get_request_container(request)
        return await container.resolve(interface)

    return cast("T", Depends(_resolver))


def resolve_controller[T](controller_cls: type[T]) -> T:
    """Return a FastAPI Depends() that resolves a class from the Arvel container.

    FastAPI resolves the Depends at request time, so the runtime type is T
    even though Depends.__init__ returns a Depends object.
    """

    async def _resolver(request: Request) -> T:
        container = getattr(request.state, "container", None)
        if container is not None:
            return await container.resolve(controller_cls)
        return controller_cls()

    return cast("T", Depends(_resolver))
