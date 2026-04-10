"""Router — route registration, groups, names, and module discovery.

Provides a thin wrapper over FastAPI's APIRouter with Laravel-like
route groups, named routes, middleware attachment, and module auto-discovery.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import wraps
from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter
from starlette.requests import Request as Request

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

from arvel.foundation.exceptions import DependencyError
from arvel.http.exceptions import RouteRegistrationError


@dataclass
class RouteGroup:
    """Configuration for a group of routes sharing prefix, middleware, and name prefix."""

    prefix: str = ""
    middleware: list[str] = field(default_factory=list)
    name: str = ""


@dataclass
class RouteEntry:
    """Internal record of a registered route."""

    path: str
    endpoint: Callable[..., object]
    methods: set[str]
    name: str | None
    middleware: list[str]
    without_middleware: list[str] = field(default_factory=list)


_RESOURCE_ACTIONS: dict[str, tuple[str, str, set[str]]] = {
    "index": ("", "", {"GET"}),
    "store": ("", "", {"POST"}),
    "show": ("/{id}", "/{id}", {"GET"}),
    "update": ("/{id}", "/{id}", {"PUT"}),
    "destroy": ("/{id}", "/{id}", {"DELETE"}),
}


def _validate_reserved_route_kwargs(route_kwargs: Mapping[str, object], *, route_name: str) -> None:
    """Reject kwargs controlled by Arvel wrapper internals."""
    for reserved in ("methods",):
        if reserved in route_kwargs:
            raise RouteRegistrationError(
                f"'{reserved}' cannot be passed here; it is set by the route helper.",
                route_name=route_name,
            )


def _validate_resource_actions(
    *,
    only: list[str] | None,
    except_: list[str] | None,
    resource_name: str,
) -> None:
    """Fail fast on unknown resource action names."""
    valid_actions = set(_RESOURCE_ACTIONS)
    if only is not None:
        unknown_only = sorted(set(only) - valid_actions)
        if unknown_only:
            raise RouteRegistrationError(
                f"Unknown actions in 'only': {', '.join(unknown_only)}",
                route_name=resource_name,
            )
    if except_ is not None:
        unknown_except = sorted(set(except_) - valid_actions)
        if unknown_except:
            raise RouteRegistrationError(
                f"Unknown actions in 'except_': {', '.join(unknown_except)}",
                route_name=resource_name,
            )


def _build_controller_endpoint(
    controller_cls: type,
    method_name: str,
    method: Callable[..., object],
) -> Callable[..., object]:
    """Create endpoint callable for class-based controller methods.

    For instance methods (first argument named ``self``), return a wrapper that:
    - Resolves/creates a controller instance at request time
    - Drops ``self`` from the public endpoint signature
    - Preserves typed params/return for OpenAPI generation

    For static/class methods, return the original callable unchanged.
    """
    signature = inspect.signature(method)
    parameters = list(signature.parameters.values())
    is_instance_method = bool(parameters) and parameters[0].name == "self"
    if not is_instance_method:
        return method

    original_param_names = [p.name for p in parameters[1:]]
    effective_parameters = list(parameters[1:])
    if "request" not in original_param_names:
        request_parameter = inspect.Parameter(
            "request",
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=Request,
        )
        effective_parameters = [request_parameter, *effective_parameters]

    endpoint_signature = signature.replace(parameters=effective_parameters)

    @wraps(method)
    async def _endpoint_proxy(*args: Any, **kwargs: Any) -> Any:
        bound_args = endpoint_signature.bind_partial(*args, **kwargs)
        request = bound_args.arguments.get("request")
        if not isinstance(request, Request):
            raise RuntimeError(
                f"Controller endpoint '{controller_cls.__name__}.{method_name}' "
                "requires a Request parameter for DI resolution."
            )

        container = getattr(request.state, "container", None)
        controller_instance: Any
        if container is not None:
            try:
                controller_instance = await container.resolve(controller_cls)
            except DependencyError as exc:
                if exc.requested_type is not controller_cls:
                    raise
                try:
                    controller_instance = controller_cls()
                except TypeError as ctor_exc:
                    raise RuntimeError(
                        f"Controller '{controller_cls.__name__}' is not bound in DI and "
                        "cannot be instantiated without arguments."
                    ) from ctor_exc
        else:
            controller_instance = controller_cls()

        call_kwargs = {
            name: value
            for name, value in bound_args.arguments.items()
            if name in original_param_names
        }
        result = getattr(controller_instance, method_name)(**call_kwargs)
        if inspect.isawaitable(result):
            return await result
        return result

    _endpoint_proxy.__dict__["__signature__"] = endpoint_signature
    return _endpoint_proxy


def _join_route_path(prefix: str, path: str) -> str:
    """Join controller prefix and route path with stable leading slash."""
    normalized_prefix = "/" + prefix.strip("/") if prefix else ""
    normalized_path = "/" + path.strip("/") if path else ""
    if normalized_path == "/":
        normalized_path = ""
    return f"{normalized_prefix}{normalized_path}" or "/"


class Router(APIRouter):
    """Route registrar with group support and duplicate name detection.

    Routes are collected here then mounted onto a FastAPI app during boot.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **cast("Any", kwargs))
        self._route_entries: list[RouteEntry] = []
        self._names: dict[str, str] = {}
        self._group_stack: list[RouteGroup] = []

    @property
    def route_entries(self) -> list[RouteEntry]:
        return list(self._route_entries)

    def _add_route(
        self,
        methods: set[str],
        path: str,
        endpoint: Callable[..., object],
        *,
        name: str | None = None,
        middleware: list[str] | None = None,
        without_middleware: list[str] | None = None,
        **fastapi_kwargs: object,
    ) -> None:
        full_path = self._current_prefix() + path
        full_name = self._current_name_prefix() + (name or "")
        full_middleware = self._current_middleware() + (middleware or [])

        resolved_name = full_name if full_name else None
        _validate_reserved_route_kwargs(fastapi_kwargs, route_name=resolved_name or full_path)

        if resolved_name and resolved_name in self._names:
            existing_path = self._names[resolved_name]
            raise RouteRegistrationError(
                f"Duplicate route name '{resolved_name}' for paths "
                f"'{existing_path}' and '{full_path}'",
                route_name=resolved_name,
                paths=[existing_path, full_path],
            )

        if resolved_name:
            self._names[resolved_name] = full_path

        route_kwargs = dict(fastapi_kwargs)
        route_kwargs["methods"] = sorted(methods)
        route_kwargs["name"] = resolved_name

        super().add_api_route(full_path, endpoint, **cast("Any", route_kwargs))
        self._route_entries.append(
            RouteEntry(
                path=full_path,
                endpoint=endpoint,
                methods=methods,
                name=resolved_name,
                middleware=full_middleware,
                without_middleware=without_middleware or [],
            )
        )

    def _register_http_method(
        self,
        method: str,
        path: str,
        endpoint: Callable[..., object] | None,
        *,
        name: str | None,
        middleware: list[str] | None,
        without_middleware: list[str] | None,
        fastapi_kwargs: dict[str, object],
    ) -> Callable[[Callable[..., object]], Callable[..., object]] | None:
        methods = {method}
        if endpoint is not None:
            self._add_route(
                methods,
                path,
                endpoint,
                name=name,
                middleware=middleware,
                without_middleware=without_middleware,
                **fastapi_kwargs,
            )
            return None

        def decorator(fn: Callable[..., object]) -> Callable[..., object]:
            self._add_route(
                methods,
                path,
                fn,
                name=name,
                middleware=middleware,
                without_middleware=without_middleware,
                **fastapi_kwargs,
            )
            return fn

        return decorator

    def get(  # type: ignore  # Supports direct-call and decorator styles.
        self,
        path: str,
        endpoint: Callable[..., object] | None = None,
        *,
        name: str | None = None,
        middleware: list[str] | None = None,
        without_middleware: list[str] | None = None,
        **fastapi_kwargs: object,
    ) -> Callable[[Callable[..., object]], Callable[..., object]] | None:
        """Register a GET route. Usable as a method call or decorator."""
        return self._register_http_method(
            "GET",
            path,
            endpoint,
            name=name,
            middleware=middleware,
            without_middleware=without_middleware,
            fastapi_kwargs=fastapi_kwargs,
        )

    def post(  # type: ignore  # Supports direct-call and decorator styles.
        self,
        path: str,
        endpoint: Callable[..., object] | None = None,
        *,
        name: str | None = None,
        middleware: list[str] | None = None,
        without_middleware: list[str] | None = None,
        **fastapi_kwargs: object,
    ) -> Callable[[Callable[..., object]], Callable[..., object]] | None:
        return self._register_http_method(
            "POST",
            path,
            endpoint,
            name=name,
            middleware=middleware,
            without_middleware=without_middleware,
            fastapi_kwargs=fastapi_kwargs,
        )

    def put(  # type: ignore  # Supports direct-call and decorator styles.
        self,
        path: str,
        endpoint: Callable[..., object] | None = None,
        *,
        name: str | None = None,
        middleware: list[str] | None = None,
        without_middleware: list[str] | None = None,
        **fastapi_kwargs: object,
    ) -> Callable[[Callable[..., object]], Callable[..., object]] | None:
        return self._register_http_method(
            "PUT",
            path,
            endpoint,
            name=name,
            middleware=middleware,
            without_middleware=without_middleware,
            fastapi_kwargs=fastapi_kwargs,
        )

    def patch(  # type: ignore  # Supports direct-call and decorator styles.
        self,
        path: str,
        endpoint: Callable[..., object] | None = None,
        *,
        name: str | None = None,
        middleware: list[str] | None = None,
        without_middleware: list[str] | None = None,
        **fastapi_kwargs: object,
    ) -> Callable[[Callable[..., object]], Callable[..., object]] | None:
        return self._register_http_method(
            "PATCH",
            path,
            endpoint,
            name=name,
            middleware=middleware,
            without_middleware=without_middleware,
            fastapi_kwargs=fastapi_kwargs,
        )

    def delete(  # type: ignore  # Supports direct-call and decorator styles.
        self,
        path: str,
        endpoint: Callable[..., object] | None = None,
        *,
        name: str | None = None,
        middleware: list[str] | None = None,
        without_middleware: list[str] | None = None,
        **fastapi_kwargs: object,
    ) -> Callable[[Callable[..., object]], Callable[..., object]] | None:
        return self._register_http_method(
            "DELETE",
            path,
            endpoint,
            name=name,
            middleware=middleware,
            without_middleware=without_middleware,
            fastapi_kwargs=fastapi_kwargs,
        )

    def resource(
        self,
        name: str,
        controller: type,
        *,
        only: list[str] | None = None,
        except_: list[str] | None = None,
        middleware: list[str] | None = None,
        **fastapi_kwargs: object,
    ) -> None:
        """Register standard CRUD routes for a resource.

        Auto-generates index, store, show, update, destroy routes with
        conventional names (``{name}.index``, ``{name}.store``, etc.).
        """
        _validate_resource_actions(only=only, except_=except_, resource_name=name)
        actions = _resolve_actions(only=only, except_=except_)
        prefix = f"/{name}"

        for action in actions:
            suffix, _param_suffix, methods = _RESOURCE_ACTIONS[action]
            path = prefix + suffix
            route_name = f"{name}.{action}"
            method_name = action
            endpoint = getattr(controller, method_name, None)
            if endpoint is None:
                msg = (
                    f"Controller {controller.__name__} is missing method "
                    f"'{method_name}' required for resource route '{route_name}'"
                )
                raise RouteRegistrationError(msg, route_name=route_name)
            endpoint = _build_controller_endpoint(controller, method_name, endpoint)
            self._add_route(
                methods,
                path,
                endpoint,
                name=route_name,
                middleware=middleware,
                **cast("Any", fastapi_kwargs),
            )

    def controller(
        self,
        controller_cls: type,
        *,
        include_resource_actions: bool = True,
    ) -> None:
        """Register controller methods declared with ``route`` decorators.

        This supports class-level defaults (``prefix``, ``tags``, ``description``,
        ``middleware``) and method-level overrides attached by
        ``arvel.http.controller.route`` decorators.
        """
        prefix = str(getattr(controller_cls, "prefix", "") or "")
        class_tags = [str(tag) for tag in getattr(controller_cls, "tags", ())]
        class_description = getattr(controller_cls, "description", None)
        class_middleware = [str(mw) for mw in getattr(controller_cls, "middleware", ())]
        raw_controller_name = controller_cls.__name__.replace("Controller", "").lower()
        controller_name = raw_controller_name.lstrip("_") or "controller"

        registered_actions: set[str] = set()
        for method_name, member in controller_cls.__dict__.items():
            meta = getattr(member, "__arvel_controller_route__", None)
            if meta is None:
                continue
            if not inspect.isfunction(member):
                continue

            method_meta = cast("Any", meta)
            registered_actions.add(method_name)
            endpoint = _build_controller_endpoint(controller_cls, method_name, member)
            merged_docs = self._merge_controller_docs(
                class_tags=class_tags,
                class_description=class_description,
                method_fastapi_kwargs=method_meta.fastapi_kwargs,
                controller_name=controller_name,
                method_name=method_name,
            )
            self._add_route(
                {method_meta.method},
                _join_route_path(prefix, method_meta.path),
                endpoint,
                name=method_meta.name or f"{controller_name}.{method_name}",
                middleware=class_middleware + method_meta.middleware,
                without_middleware=method_meta.without_middleware,
                **merged_docs,
            )

        if not include_resource_actions:
            return

        for action, (suffix, _, methods) in _RESOURCE_ACTIONS.items():
            if action in registered_actions:
                continue
            member = getattr(controller_cls, action, None)
            if member is None or not inspect.isfunction(member):
                continue
            endpoint = _build_controller_endpoint(controller_cls, action, member)
            self._add_route(
                methods,
                _join_route_path(prefix, suffix),
                endpoint,
                name=f"{controller_name}.{action}",
                middleware=class_middleware,
                **cast(
                    "Any",
                    self._merge_controller_docs(
                        class_tags=class_tags,
                        class_description=class_description,
                        method_fastapi_kwargs={},
                        controller_name=controller_name,
                        method_name=action,
                    ),
                ),
            )

    @staticmethod
    def _merge_controller_docs(
        *,
        class_tags: list[str],
        class_description: str | None,
        method_fastapi_kwargs: dict[str, object],
        controller_name: str,
        method_name: str,
    ) -> dict[str, object]:
        merged = dict(method_fastapi_kwargs)
        if class_tags and "tags" not in merged:
            merged["tags"] = class_tags
        if class_description is not None and "description" not in merged:
            merged["description"] = class_description
        if "operation_id" not in merged:
            merged["operation_id"] = f"{controller_name}_{method_name}"
        return merged

    def url_for(self, name: str, **params: str | int) -> str:
        """Generate a URL path from a named route.

        Raises:
            RouteRegistrationError: If the route name is not registered.
        """
        path_template = self._names.get(name)
        if path_template is None:
            raise RouteRegistrationError(
                f"No route named '{name}' is registered",
                route_name=name,
            )
        try:
            return path_template.format(**params)
        except KeyError as exc:
            raise RouteRegistrationError(
                f"Missing parameter {exc} for route '{name}' with path '{path_template}'",
                route_name=name,
            ) from exc

    @contextmanager
    def group(
        self,
        *,
        prefix: str = "",
        middleware: list[str] | None = None,
        name: str = "",
    ):
        """Context manager that applies route grouping metadata.

        Preferred form:
        - ``router.group(prefix="/api", middleware=["auth"], name="api.")``
        """
        resolved_group = RouteGroup(
            prefix=prefix,
            middleware=list(middleware or []),
            name=name,
        )

        self._group_stack.append(resolved_group)
        try:
            yield self
        finally:
            self._group_stack.pop()

    def _current_prefix(self) -> str:
        return "".join(g.prefix for g in self._group_stack)

    def _current_name_prefix(self) -> str:
        return "".join(g.name for g in self._group_stack)

    def _current_middleware(self) -> list[str]:
        mw: list[str] = []
        for g in self._group_stack:
            mw.extend(g.middleware)
        return mw


def _resolve_actions(
    *,
    only: list[str] | None = None,
    except_: list[str] | None = None,
) -> list[str]:
    """Determine which CRUD actions to register."""
    all_actions = list(_RESOURCE_ACTIONS.keys())
    if only is not None:
        return [a for a in all_actions if a in only]
    if except_ is not None:
        return [a for a in all_actions if a not in except_]
    return all_actions


def discover_routes(base_path: Path) -> list[tuple[str, Router]]:
    """Scan ``routes/*.py`` for Router exports.

    Each Python file in ``routes/`` that exports a module-level ``router``
    (an instance of ``Router``) is collected. Files starting with ``_``
    are skipped.

    Returns a list of ``(name, router)`` tuples sorted alphabetically.
    """
    routes_dir = base_path / "routes"
    if not routes_dir.exists():
        return []

    results: list[tuple[str, Router]] = []
    for f in sorted(routes_dir.iterdir()):
        if not f.is_file() or f.suffix != ".py" or f.name.startswith("_"):
            continue

        name = f.stem
        spec = importlib.util.spec_from_file_location(f"routes.{name}", str(f))
        if spec is None or spec.loader is None:
            continue

        module = importlib.util.module_from_spec(spec)
        sys.modules[f"routes.{name}"] = module
        spec.loader.exec_module(module)

        router = getattr(module, "router", None)
        if router is not None and isinstance(router, Router):
            results.append((name, router))

    return results
