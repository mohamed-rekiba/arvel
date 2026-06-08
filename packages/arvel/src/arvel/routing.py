"""Routing facade + Router + RouteServiceProvider.

Wraps ``fastapi.APIRouter`` with the Laravel route DSL. ``docs/api/http-api.md`` §arvel.routing.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import inspect
import os
import re
import sys
import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from functools import wraps
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, TypeGuard, TypeVar, cast
from urllib.parse import urlencode

from starlette.requests import Request

from arvel.http.exceptions import AuthorizationException, NotFoundException
from arvel.http.middleware import Middleware
from arvel.http.requests import FormRequest
from arvel.providers.service_provider import ServiceProvider
from arvel.support.pipeline import Pipeline
from arvel.support.secure_compare import constant_time_equals

if TYPE_CHECKING:
    from fastapi import FastAPI

    from arvel.database.model import Model

MiddlewareRef = Middleware | str


_HANDLERS_HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")

# TypeVar that binds the decorated handler's exact type so the decorator
# returns the same function — preserving parameter and return types
# at every call site instead of erasing them to Callable[..., Awaitable[Any]].
_H = TypeVar("_H", bound=Callable[..., Awaitable[Any]])


class _SignatureCarrier(Protocol):
    """Anything whose runtime signature can be overridden via ``__signature__``.

    Functions accept this attribute at runtime (``inspect.signature`` reads
    it), but typeshed doesn't declare it writable. Casting to this Protocol
    lets us assign without ``# type: ignore[attr-defined]``.
    """

    __signature__: inspect.Signature


RouteBindingResolver = Callable[[str], Awaitable[Any]]


@dataclass(slots=True)
class _GroupFrame:
    prefix: str = ""
    middleware: tuple[MiddlewareRef, ...] = ()
    name_prefix: str = ""
    tags: tuple[str, ...] = ()
    bindings: dict[str, RouteBindingResolver] = field(
        default_factory=dict[str, RouteBindingResolver]
    )


_group_stack: ContextVar[tuple[_GroupFrame, ...]] = ContextVar(
    "arvel_route_group_stack", default=()
)


def _current_prefix() -> str:
    return "".join(frame.prefix for frame in _group_stack.get())


def _current_middleware() -> tuple[Middleware, ...]:
    out: list[Middleware] = []
    for frame in _group_stack.get():
        out.extend(Router.singleton().resolve_middleware(frame.middleware))
    return tuple(out)


def _current_name_prefix() -> str:
    return "".join(frame.name_prefix for frame in _group_stack.get())


def _current_tags() -> tuple[str, ...]:
    # Stack outermost → innermost; dedupe while preserving order.
    seen: dict[str, None] = {}
    for frame in _group_stack.get():
        for tag in frame.tags:
            seen.setdefault(tag, None)
    return tuple(seen)


def _current_bindings() -> dict[str, RouteBindingResolver]:
    # Stack outermost → innermost; inner groups override outer.
    merged: dict[str, RouteBindingResolver] = {}
    for frame in _group_stack.get():
        merged.update(frame.bindings)
    return merged


@dataclass(slots=True)
class RouteSpec:
    """A buffered route. Mounted into a FastAPI app by ``Router.register_with_app``."""

    method: str
    path: str
    handler: Callable[..., Awaitable[Any]]
    name: str | None = None
    middleware: tuple[Middleware, ...] = ()
    controller: type | None = None
    # Method-based controller dispatch. When set, ``Router.register_with_app``
    # resolves ``controller`` through the container and binds to ``action``.
    # When ``None`` and the controller has a ``__call__``, the invokable adapter
    # is used instead.
    action: str | None = None
    extras: dict[str, Any] = field(default_factory=dict[str, Any])
    # Captured at decoration time so closure-scope types (e.g., FormRequest subclasses
    # declared inside test functions or factory functions) can be resolved later.
    caller_locals: dict[str, Any] = field(default_factory=dict[str, Any])
    # Custom param resolvers visible at decoration time — group bindings stack
    # outermost→innermost, then merged with global bindings (global is lowest
    # precedence). Captured here so per-group scoping persists after the
    # ``with Route.group()`` block exits.
    bindings: dict[str, RouteBindingResolver] = field(
        default_factory=dict[str, RouteBindingResolver]
    )


class Router:
    """Buffer of declared routes. One per app; use ``Router.singleton()``."""

    _instance: ClassVar[Router | None] = None

    def __init__(self) -> None:
        self._routes: list[RouteSpec] = []
        # Bindings registered at module scope (outside any ``Route.group()``).
        # Applied to every route unless an inner group overrides them.
        self._global_bindings: dict[str, RouteBindingResolver] = {}
        self._middleware_groups: dict[str, tuple[MiddlewareRef, ...]] = {}

    # ───── Lifecycle ─────

    @classmethod
    def singleton(cls) -> Router:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_singleton(cls) -> None:
        cls._instance = None

    # ───── Internal: buffer ─────

    def _add(self, spec: RouteSpec) -> None:
        self._routes.append(spec)

    def routes(self) -> list[RouteSpec]:
        return list(self._routes)

    def bindings(self) -> dict[str, RouteBindingResolver]:
        """Snapshot of currently registered global parameter resolvers."""
        return dict(self._global_bindings)

    def middleware_group(self, name: str, middleware: Sequence[MiddlewareRef]) -> None:
        """Register a named middleware group."""
        self._middleware_groups[name] = tuple(middleware)

    def middleware(self, name: str, middleware: Middleware) -> None:
        """Register a single named middleware."""
        self.middleware_group(name, [middleware])

    def resolve_middleware(
        self,
        middleware: Sequence[MiddlewareRef],
        *,
        _seen: frozenset[str] = frozenset(),
    ) -> tuple[Middleware, ...]:
        resolved: list[Middleware] = []
        for item in middleware:
            if not isinstance(item, str):
                resolved.append(item)
                continue
            if item in _seen:
                raise ValueError(f"Middleware group cycle detected: {item}")
            group = self._middleware_groups.get(item)
            if group is None:
                raise ValueError(f"Unknown middleware group: {item}")
            resolved.extend(self.resolve_middleware(group, _seen=_seen | {item}))
        return tuple(resolved)

    def _register_binding(self, name: str, resolver: RouteBindingResolver) -> None:
        self._global_bindings[name] = resolver

    # ───── Mount to FastAPI ─────

    def register_with_app(self, app: FastAPI) -> None:
        container = getattr(getattr(app, "state", None), "arvel_container", None)
        for spec in self._routes:
            handler = spec.handler
            if spec.controller is not None:
                # _make_decorator already rejected controllers with neither
                # action nor __call__, so the else branch is unreachable.
                if spec.action is not None:
                    handler = MethodControllerAdapter(
                        spec.controller, spec.action, container=container
                    ).build()
                else:
                    handler = _invokable_controller_adapter(spec.controller, container=container)
            # Order matters: model binding wraps the original handler first so
            # the FormRequest layer (which inspects the *current* signature)
            # never sees the Model parameter that's already been swapped out.
            handler = _normalize_model_bindings(
                handler, spec.caller_locals, explicit_bindings=spec.bindings
            )
            handler = _normalize_form_requests(handler, spec.caller_locals)
            # Rewrite string annotations (PEP 563 / from __future__ import annotations)
            # to concrete types before FastAPI inspects the signature. Handlers defined
            # in factory methods use locally-imported types that aren't in the handler's
            # __globals__, so FastAPI can't resolve them without this step.
            handler = _resolve_handler_signature(handler, spec.caller_locals)
            wrapped = _wrap_with_middleware(handler, spec.middleware, spec.caller_locals)
            # Routes with an explicit response_model already control their output
            # shape; for the rest, keep a bare ``return model`` from leaking
            # __hidden__ columns through FastAPI's dataclass encoder.
            if "response_model" not in spec.extras:
                wrapped = _wrap_response_normalizer(wrapped)
            app.add_api_route(
                spec.path,
                wrapped,
                methods=[spec.method],
                name=spec.name,
                **spec.extras,
            )


def _has_invokable_call(cls: type) -> bool:
    """True iff ``cls`` defines its own ``__call__`` method (i.e. is invokable)."""
    return any("__call__" in base.__dict__ for base in cls.__mro__ if base is not object)


async def _controller_marker() -> None:
    """Stand-in handler for controller routes registered without a function.

    ``Router.register_with_app`` swaps this out for the real adapter — see
    ``MethodControllerAdapter``. The body never runs at request time.
    """
    return


# ───────────────────────── Resource controllers ──────────────────────────


# Default RESTful action set, in route-mounting order. Matches Laravel.
_RESOURCE_ACTIONS: tuple[str, ...] = (
    "index",
    "create",
    "store",
    "show",
    "edit",
    "update",
    "destroy",
)

# Per-action HTTP method + path-suffix template. ``{p}`` is the member
# parameter (singular of the resource name, or whatever ``parameter=`` set).
_RESOURCE_SHAPES: dict[str, tuple[str, str]] = {
    "index": ("GET", ""),
    "create": ("GET", "/create"),
    "store": ("POST", ""),
    "show": ("GET", "/{p}"),
    "edit": ("GET", "/{p}/edit"),
    "update": ("PUT", "/{p}"),
    "destroy": ("DELETE", "/{p}"),
}

# Actions that don't make sense for JSON-only APIs (HTML form helpers).
_HTML_ONLY_ACTIONS: frozenset[str] = frozenset({"create", "edit"})


_IES_MIN_LEN = 4  # "pies" → "pie", but leave "ies" alone — too short to be a plural.
_SIBILANT_SUFFIXES: tuple[str, ...] = ("ses", "xes", "zes")


def _resource_singular(plural: str) -> str:
    """Best-effort English singularisation for resource path parameters.

    Covers the patterns Arvel users hit in practice. Override via the
    ``parameter=`` kwarg on ``Route.resource()`` when the heuristic is wrong.
    """
    if plural.endswith("ies") and len(plural) >= _IES_MIN_LEN:
        return f"{plural[:-3]}y"
    if plural.endswith(_SIBILANT_SUFFIXES):
        return plural[:-2]
    if plural.endswith("s") and not plural.endswith("ss"):
        return plural[:-1]
    return plural


class ResourceRegistration:
    """Fluent builder returned by ``Route.resource()``.

    Owns the ``RouteSpec`` instances created at construction time so the
    ``only`` / ``except_`` / ``names`` methods can mutate them in place.
    Removed actions are deregistered from the router; renamed routes have
    their ``RouteSpec.name`` updated.
    """

    def __init__(
        self,
        prefix: str,
        controller: type,
        *,
        parameter: str | None = None,
        middleware: Sequence[MiddlewareRef] | None = None,
        actions: Sequence[str] = _RESOURCE_ACTIONS,
    ) -> None:
        # Strip a trailing slash but keep the leading one — ``/posts/`` and
        # ``/posts`` should produce the same routes.
        prefix = prefix.rstrip("/") if prefix != "/" else prefix
        resource_name = prefix.lstrip("/").split("/")[-1] or controller.__name__.lower()
        self._prefix = prefix
        self._controller = controller
        self._resource_name = resource_name
        self._parameter = parameter or _resource_singular(resource_name)
        self._middleware = tuple(middleware or ())
        # Map action → spec so removals and renames are O(1).
        self._owned: dict[str, RouteSpec] = {}
        self._register(actions)

    # ───────── Registration ─────────

    def _register(self, actions: Sequence[str]) -> None:
        # _make_decorator already prepends _current_prefix(); pass the prefix
        # relative to that context so group-scoped resources stack cleanly.
        for action in actions:
            if action not in _RESOURCE_SHAPES:
                msg = f"{action!r} is not a resource action."
                raise ValueError(msg)
            method, suffix = _RESOURCE_SHAPES[action]
            relative_path = self._prefix + suffix.replace("{p}", "{" + self._parameter + "}")
            decorator = _RouteFacade._make_decorator(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]  # ResourceRegistration is the sibling builder
                method,
                relative_path,
                name=f"{self._resource_name}.{action}",
                middleware=self._middleware,
                controller=self._controller,
                action=action,
                extras={},
            )
            del decorator  # eager registration fires inside _make_decorator
            spec = Router.singleton().routes()[-1]
            self._owned[action] = spec

    # ───────── Fluent filters ─────────

    def only(self, *actions: str | Sequence[str]) -> ResourceRegistration:
        """Restrict the registration to the listed actions."""
        keep = self._flatten(actions)
        self._validate(keep)
        for action in list(self._owned):
            if action not in keep:
                self._drop(action)
        return self

    def except_(self, *actions: str | Sequence[str]) -> ResourceRegistration:
        """Drop the listed actions from the registration."""
        drop = self._flatten(actions)
        self._validate(drop)
        for action in drop:
            if action in self._owned:
                self._drop(action)
        return self

    def names(self, mapping: Mapping[str, str]) -> ResourceRegistration:
        """Override the default ``<resource>.<action>`` names per-action."""
        for action, new_name in mapping.items():
            self._validate({action})
            if action in self._owned:
                self._owned[action].name = new_name
        return self

    # ───────── Internals ─────────

    @staticmethod
    def _flatten(items: tuple[str | Sequence[str], ...]) -> set[str]:
        out: set[str] = set()
        for item in items:
            if isinstance(item, str):
                out.add(item)
            else:
                out.update(item)
        return out

    @staticmethod
    def _validate(actions: set[str]) -> None:
        unknown = actions - set(_RESOURCE_SHAPES)
        if unknown:
            msg = f"{next(iter(unknown))!r} is not a resource action."
            raise ValueError(msg)

    def _drop(self, action: str) -> None:
        spec = self._owned.pop(action)
        Router.singleton()._routes.remove(spec)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]  # ResourceRegistration is the sibling builder


def _invokable_controller_adapter(
    cls: type,
    container: Any = None,
) -> Callable[..., Awaitable[Any]]:
    """Wrap an invokable controller class as an async handler FastAPI can route to.

    Resolves a fresh instance per request (Laravel parity, no cross-request state
    bleed). The probe built here only validates DI at mount and reads ``__call__``'s
    signature, then is discarded.
    """

    def _make() -> Any:
        return container.make(cls) if container is not None else cls()

    probe_call = _make().__call__
    if not callable(probe_call):
        msg = f"{cls.__qualname__} is bound as an invokable controller but has no __call__."
        raise TypeError(msg)

    sig = inspect.signature(probe_call)

    @wraps(probe_call)
    async def handler(**kwargs: Any) -> Any:
        result: Any = _make().__call__(**kwargs)
        if inspect.isawaitable(result):
            return await result
        return result

    cast("_SignatureCarrier", handler).__signature__ = sig
    return handler


class MethodControllerAdapter:
    """Bind a controller method to an HTTP route, resolving the class through DI.

    Laravel's controller routing — ``Route::get('/posts/{post}', [PostController::class,
    'show'])`` — boils down to two things: instantiate the controller through the
    container so constructor deps get injected, then call the named method with the
    framework-resolved arguments. This adapter does both:

    1. ``container.make(cls)`` (or ``cls()`` when no container is registered)
       hands back an instance with deps wired up.
    2. The method's own signature is copied onto the wrapper so FastAPI can keep
       resolving path / query / body params from it.

    The adapter is exposed publicly so applications can build their own routers
    on top of the same plumbing.
    """

    def __init__(self, cls: type, action: str, *, container: Any = None) -> None:
        if not action:
            msg = "MethodControllerAdapter requires a non-empty action name."
            raise ValueError(msg)
        if not hasattr(cls, action):
            msg = f"{cls.__qualname__} has no method named {action!r}."
            raise AttributeError(msg)
        self.cls = cls
        self.action = action
        self.container = container

    def _instantiate(self) -> Any:
        if self.container is not None:
            return self.container.make(self.cls)
        return self.cls()

    def build(self) -> Callable[..., Awaitable[Any]]:
        """Return an async handler that resolves a fresh controller per request.

        The probe instance built here is only used to validate DI wiring at mount
        (fail fast at boot, not on first request) and to read the bound method's
        signature — which already has the receiver stripped, so static/class
        methods need no special casing. It is then discarded: every request gets
        its own instance, so per-request ``self`` state never bleeds across
        requests. Matches Laravel, which resolves the controller per request.
        """
        probe = self._instantiate()
        probe_method: Any = getattr(probe, self.action)
        if not callable(probe_method):
            msg = f"{self.cls.__qualname__}.{self.action} is not callable."
            raise TypeError(msg)

        sig = inspect.signature(probe_method)

        @wraps(probe_method)
        async def handler(**kwargs: Any) -> Any:
            method: Any = getattr(self._instantiate(), self.action)
            result: Any = method(**kwargs)
            if inspect.isawaitable(result):
                return await result
            return result

        cast("_SignatureCarrier", handler).__signature__ = sig
        return handler


# ───────────────────────── Annotation resolution ─────────────────────────────


def _resolve_handler_signature(
    handler: Callable[..., Awaitable[Any]],
    caller_locals: dict[str, Any] | None = None,
) -> Callable[..., Awaitable[Any]]:
    """Return handler with string annotations replaced by their concrete types.

    Handlers defined inside factory methods (e.g. ``AuthServiceProvider._mount_routes``)
    live in modules that use ``from __future__ import annotations``. Every annotation
    becomes a string at runtime. FastAPI resolves these strings through the handler's
    ``__globals__``, but locally-imported types aren't there — so FastAPI falls back to
    treating the parameters as query params. Rewriting ``__signature__`` with the resolved
    types fixes that without any change at the call site.
    """
    sig = inspect.signature(handler)
    if not any(isinstance(p.annotation, str) for p in sig.parameters.values()):
        return handler

    resolved = _resolve_annotations(handler, caller_locals)
    new_params = [
        p.replace(annotation=resolved.get(p.name, p.annotation)) for p in sig.parameters.values()
    ]
    ret = sig.return_annotation
    if isinstance(ret, str):
        ret = resolved.get("return", ret)

    @wraps(handler)
    async def wrapped(**kwargs: Any) -> Any:
        return await handler(**kwargs)

    cast("_SignatureCarrier", wrapped).__signature__ = sig.replace(
        parameters=new_params,
        return_annotation=ret,
    )
    return wrapped


# ───────────────────────── FormRequest normalization ─────────────────────────


_FORM_BODY_PREFIX = "__arvel_form_body__"


def _is_form_request_subclass(ann: object) -> TypeGuard[type[FormRequest[Any]]]:
    """TypeGuard that both mypy and pyright narrow to type[FormRequest[Any]]."""
    return isinstance(ann, type) and issubclass(ann, FormRequest)


def _normalize_form_requests(
    handler: Callable[..., Awaitable[Any]],
    caller_locals: dict[str, Any] | None = None,
) -> Callable[..., Awaitable[Any]]:
    """Rewrite handler signature so ``form: SomeFormRequest`` works under FastAPI.

    For every parameter whose annotation is a ``FormRequest`` subclass we:
    1. Drop the original param from the FastAPI-visible signature.
    2. Add ``__arvel_form_body__<name>: PayloadModel`` (FastAPI parses the body).
    3. In the wrapper, construct ``FormRequestSubclass(payload)``, await
       ``authorize(request)``, and pass the instance back under the original name.
    """
    original_sig = inspect.signature(handler)
    resolved = _resolve_annotations(handler, caller_locals)
    form_params: dict[str, tuple[type[FormRequest[Any]], type[Any]]] = {}
    for name in original_sig.parameters:
        ann = resolved.get(name, original_sig.parameters[name].annotation)
        if _is_form_request_subclass(ann):
            fr_cls = ann
            payload_type: type[Any] | None = getattr(fr_cls, "_payload_type", None)
            if payload_type is None:
                msg = (
                    f"FormRequest subclass {fr_cls.__qualname__} did not capture its payload "
                    f"type. Subclass as `class X(FormRequest[Payload]):`."
                )
                raise TypeError(msg)
            form_params[name] = (fr_cls, payload_type)

    if not form_params:
        return handler

    # Build the new FastAPI-facing signature.
    new_params: list[inspect.Parameter] = []
    for name, param in original_sig.parameters.items():
        if name in form_params:
            continue
        resolved_ann = resolved.get(name, param.annotation)
        new_params.append(
            param.replace(kind=inspect.Parameter.KEYWORD_ONLY, annotation=resolved_ann)
        )

    for name, (_form_cls, payload_type) in form_params.items():
        new_params.append(
            inspect.Parameter(
                f"{_FORM_BODY_PREFIX}{name}",
                inspect.Parameter.KEYWORD_ONLY,
                annotation=payload_type,
            )
        )

    # Always inject a Request so authorize() can see it.
    request_kw = "__arvel_form_request__"
    new_params.append(
        inspect.Parameter(
            request_kw,
            inspect.Parameter.KEYWORD_ONLY,
            annotation=Request,
        )
    )

    @wraps(handler)
    async def wrapped(**kwargs: Any) -> Any:
        request = kwargs.pop(request_kw)
        handler_kwargs: dict[str, Any] = {}
        for name, (form_cls, _payload_type) in form_params.items():
            payload = kwargs.pop(f"{_FORM_BODY_PREFIX}{name}")
            form = form_cls(payload)
            await form.validate_rules(request)
            allowed = await form.authorize(request)
            if not allowed:
                raise AuthorizationException("Not authorized.")
            handler_kwargs[name] = form
        handler_kwargs.update(kwargs)
        return await handler(**handler_kwargs)

    cast("_SignatureCarrier", wrapped).__signature__ = original_sig.replace(parameters=new_params)
    return wrapped


# ───────────────────────── Implicit route model binding ─────────────────────


def _is_model_subclass(ann: object) -> TypeGuard[type[Model]]:
    """TypeGuard for Arvel ``Model`` subclasses.

    Imports ``Model`` lazily so the routing module stays usable in apps that
    don't pull in SQLAlchemy.
    """
    try:
        from arvel.database.model import Model as _Model
    except ImportError:
        return False
    return isinstance(ann, type) and issubclass(ann, _Model)


def _coerce_models_in_result(result: Any) -> Any:
    """Route raw model returns through ``to_dict()`` so ``__hidden__`` is honoured.

    FastAPI serialises an Arvel ``Model`` as a plain dataclass — every mapped
    column, including ones a model marks ``__hidden__`` (password hashes, tokens).
    Laravel's ``return $user;`` hides those; ours leaked them. Convert a returned
    model, or a list of them, to its ``to_dict()`` form before FastAPI encodes it.
    ``to_dict`` only reads columns, so no async relation load happens here.

    Anything that isn't a model (dicts, Pydantic models, ``Response`` objects,
    primitives) passes through untouched.
    """
    try:
        from arvel.database.model import Model as _Model
    except ImportError:
        return result
    if isinstance(result, _Model):
        return result.to_dict()
    if isinstance(result, list):
        # cast to list[object] (not list[Any]): keeps pyright's element type known
        # without mypy flagging a redundant cast off its own list[Any] narrowing.
        items: list[object] = cast("list[object]", result)
        if any(isinstance(item, _Model) for item in items):
            return [item.to_dict() if isinstance(item, _Model) else item for item in items]
        return items
    return result


def _wrap_response_normalizer(
    handler: Callable[..., Awaitable[Any]],
) -> Callable[..., Awaitable[Any]]:
    """Wrap *handler* so raw model returns honour ``__hidden__`` (see above).

    Preserves the handler's ``__signature__`` so FastAPI still resolves
    parameters and dependencies unchanged.
    """

    @wraps(handler)
    async def wrapped(**kwargs: Any) -> Any:
        return _coerce_models_in_result(await handler(**kwargs))

    sig = getattr(handler, "__signature__", None)
    if sig is not None:
        cast("_SignatureCarrier", wrapped).__signature__ = sig
    return wrapped


def _route_key_for(model_cls: type[Model]) -> str | None:
    """Return the column name to look up from the URL, or ``None`` for PK."""
    key = getattr(model_cls, "route_key_name", None)
    if key is None or not isinstance(key, str):
        return None
    return key


async def _resolve_route_binding(model_cls: type[Model], raw_value: str) -> Any:
    """Look up a model from a URL parameter. Returns the instance or raises 404."""
    route_key = _route_key_for(model_cls)
    instance: Any
    if route_key is None:
        instance = await model_cls.find(raw_value)
    else:
        instance = await model_cls.where(**{route_key: raw_value}).first()
    if instance is None:
        msg = f"{model_cls.__name__} not found."
        raise NotFoundException(msg)
    return instance


class ImplicitRouteModelBinder:
    """Inspects a handler's signature and resolves ``param: Model`` arguments from the DB.

    Registered automatically by ``Router.register_with_app``. Users normally
    don't construct this directly — exposed so apps that wire FastAPI themselves
    can opt in, and so the binding logic can be unit-tested without spinning
    up an HTTP server.
    """

    def model_parameters(
        self,
        handler: Callable[..., Any],
        *,
        caller_locals: dict[str, Any] | None = None,
    ) -> dict[str, type[Model]]:
        """Return a mapping of ``{param_name: Model subclass}`` for the handler."""
        sig = inspect.signature(handler)
        resolved = _resolve_annotations(handler, caller_locals)
        out: dict[str, type[Model]] = {}
        for name in sig.parameters:
            ann = resolved.get(name, sig.parameters[name].annotation)
            if _is_model_subclass(ann):
                out[name] = ann
        return out


_DEFAULT_BINDER = ImplicitRouteModelBinder()


def _normalize_model_bindings(
    handler: Callable[..., Awaitable[Any]],
    caller_locals: dict[str, Any] | None = None,
    *,
    explicit_bindings: dict[str, RouteBindingResolver] | None = None,
) -> Callable[..., Awaitable[Any]]:
    """Rewrite handler signature so model-typed params resolve from the DB.

    Two flavours of binding cohabit on the same wrapper:

    - **Implicit**: every parameter whose annotation is a ``Model`` subclass
      gets resolved through ``Model.find`` (or ``Model.where(<route_key>=raw)``
      when ``route_key_name`` is set).
    - **Explicit**: any parameter name registered via ``Route.bind(name, resolver)``
      gets resolved by the user-supplied resolver, regardless of annotation.
      Explicit resolvers win over implicit binding when both apply.

    A resolved ``None`` raises ``NotFoundException`` (404).
    """
    bindings = explicit_bindings or {}
    model_params = _DEFAULT_BINDER.model_parameters(handler, caller_locals=caller_locals)
    original_sig = inspect.signature(handler)
    explicit_names = {name for name in bindings if name in original_sig.parameters}

    rewritten_names = set(model_params) | explicit_names
    if not rewritten_names:
        return handler

    resolved = _resolve_annotations(handler, caller_locals)

    new_params: list[inspect.Parameter] = []
    for name, param in original_sig.parameters.items():
        if name in rewritten_names:
            new_params.append(param.replace(kind=inspect.Parameter.KEYWORD_ONLY, annotation=str))
            continue
        resolved_ann = resolved.get(name, param.annotation)
        new_params.append(
            param.replace(kind=inspect.Parameter.KEYWORD_ONLY, annotation=resolved_ann)
        )

    @wraps(handler)
    async def wrapped(**kwargs: Any) -> Any:
        handler_kwargs: dict[str, Any] = dict(kwargs)
        for name in rewritten_names:
            raw = handler_kwargs.pop(name)
            if name in explicit_names:
                instance = await bindings[name](raw)
                if instance is None:
                    msg = f"Route parameter '{name}' could not be resolved."
                    raise NotFoundException(msg)
                handler_kwargs[name] = instance
            else:
                handler_kwargs[name] = await _resolve_route_binding(model_params[name], raw)
        return await handler(**handler_kwargs)

    cast("_SignatureCarrier", wrapped).__signature__ = original_sig.replace(parameters=new_params)
    # @wraps copied the original __annotations__ in, but downstream middleware
    # wrappers consult typing.get_type_hints() (which reads __annotations__
    # rather than __signature__). Force the two to agree so the rewritten
    # `param: str` reaches FastAPI as a path-string param, not the original
    # Model class.
    wrapped.__annotations__ = {**wrapped.__annotations__}
    for name in rewritten_names:
        wrapped.__annotations__[name] = str
    return wrapped


_ARVEL_REQ_KW = "__arvel_request__"


def _resolve_annotations(
    handler: Callable[..., Any],
    caller_locals: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve string (PEP 563) annotations to runtime types.

    Thin shim over :func:`arvel.support.annotations.resolve_annotations` that
    pre-populates the Arvel-aware fallback namespace (``Request``,
    ``FormRequest``). Kept as a private name so existing call sites in this
    module stay readable; new callers should import directly from
    ``arvel.support.annotations``.
    """
    from arvel.support.annotations import resolve_annotations as _resolve

    return _resolve(
        handler,
        caller_locals=caller_locals,
        extra_namespace={"Request": Request, "FormRequest": FormRequest},
    )


def _wrap_with_middleware(
    handler: Callable[..., Awaitable[Any]],
    middlewares: Sequence[Middleware],
    caller_locals: dict[str, Any] | None = None,
) -> Callable[..., Awaitable[Any]]:
    if not middlewares:
        return handler

    # Adapt every arvel Middleware to the arvel.support.Pipeline shape.
    pipeline_steps: list[Callable[[Any, Callable[[Any], Awaitable[Any]]], Awaitable[Any]]] = []
    for mw in middlewares:

        async def step(
            request: Any,
            nxt: Callable[[Any], Awaitable[Any]],
            *,
            _mw: Middleware = mw,
        ) -> Any:
            return await _mw.handle(request, nxt)

        pipeline_steps.append(step)

    original_sig = inspect.signature(handler)
    resolved = _resolve_annotations(handler, caller_locals)

    # If the user already declared a Request parameter, reuse it (FastAPI injects only
    # one Request even when several params share the annotation).
    user_request_name: str | None = None
    for name in original_sig.parameters:
        ann = resolved.get(name, original_sig.parameters[name].annotation)
        if ann is Request:
            user_request_name = name
            break

    if user_request_name is None:
        request_key = _ARVEL_REQ_KW
    else:
        request_key = user_request_name

    @wraps(handler)
    async def wrapped(**kwargs: Any) -> Any:
        if user_request_name is None:
            request = kwargs.pop(request_key)
        else:
            request = kwargs[request_key]

        async def final(_req: Any) -> Any:
            return await handler(**kwargs)

        return await Pipeline[Any, Any]().send(request).through(pipeline_steps).then(final)

    new_params = [
        p.replace(
            kind=inspect.Parameter.KEYWORD_ONLY,
            annotation=resolved.get(p.name, p.annotation),
        )
        for p in original_sig.parameters.values()
    ]
    if user_request_name is None:
        new_params.append(
            inspect.Parameter(
                _ARVEL_REQ_KW,
                inspect.Parameter.KEYWORD_ONLY,
                annotation=Request,
            )
        )
    cast("_SignatureCarrier", wrapped).__signature__ = original_sig.replace(parameters=new_params)
    return wrapped


# ───────────────────────── Route facade ─────────────────────────


class _RouteFacade:
    """Public ``Route`` facade — module-level singleton."""

    @staticmethod
    def _make_decorator(
        method: str,
        path: str,
        *,
        name: str | None,
        middleware: Sequence[MiddlewareRef] | None,
        controller: type | None,
        action: str | None,
        extras: dict[str, Any],
    ) -> Callable[[_H], _H]:
        # Capture the caller's locals so closure-scope types (FormRequest subclasses
        # declared inside test functions) can be resolved later. This is a one-shot
        # snapshot; it does not retain a reference to the caller's frame.
        caller_frame = sys._getframe(2)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]  # frame walking is intentional for closure-scope capture
        caller_locals = dict(caller_frame.f_locals)

        # Snapshot group state up front; capturing later inside the decorator
        # closure would pick up whatever group is active at decoration time,
        # not at _make_decorator() time. Same for the bindings merge.
        final_name = f"{_current_name_prefix()}{name}" if name is not None else None
        full_path = f"{_current_prefix()}{path}"
        full_middleware = (
            *_current_middleware(),
            *Router.singleton().resolve_middleware(middleware or ()),
        )
        spec_bindings: dict[str, RouteBindingResolver] = dict(Router.singleton().bindings())
        spec_bindings.update(_current_bindings())
        # Group tags prepend per-route tags; flow through extras to add_api_route.
        group_tags = _current_tags()
        full_extras = dict(extras)
        if group_tags:
            route_tags = tuple(full_extras.get("tags") or ())
            full_extras["tags"] = [*group_tags, *route_tags]

        def _register(handler: Callable[..., Awaitable[Any]]) -> None:
            spec = RouteSpec(
                method=method.upper(),
                path=full_path,
                handler=handler,
                name=final_name,
                middleware=full_middleware,
                controller=controller,
                action=action,
                extras=full_extras,
                caller_locals=caller_locals,
                bindings=spec_bindings,
            )
            Router.singleton()._add(spec)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]  # Router._add is sibling-module-private; Route is the only authorized caller

        # With ``controller=``, the registered handler is irrelevant —
        # ``Router.register_with_app`` swaps it for the real adapter
        # (method-based when ``action`` is set, invokable when the class
        # defines ``__call__``). Register eagerly and hand back a no-op
        # decorator so the binding is one expression. Misuse — a controller
        # with neither ``action`` nor ``__call__`` — surfaces here rather
        # than at mount time.
        if controller is not None:
            if action is None and not _has_invokable_call(controller):
                msg = (
                    f"{controller.__qualname__} has no __call__; bind a specific "
                    f'method via `action="method_name"` on the route decorator.'
                )
                raise TypeError(msg)
            _register(_controller_marker)

            def noop_decorator(handler: _H) -> _H:
                return handler

            return noop_decorator

        def decorator(handler: _H) -> _H:
            _register(handler)
            return handler

        return decorator

    def bind(self, name: str, resolver: RouteBindingResolver) -> None:
        """Register a custom resolver for routes whose path parameter is ``name``.

        Outside any ``Route.group()`` block, the resolver applies globally.
        Inside a group, it's scoped to that group (and any nested groups
        unless they override it for the same name). The resolver receives
        the raw URL value as a string; returning ``None`` produces a 404.
        """
        stack = _group_stack.get()
        if stack:
            stack[-1].bindings[name] = resolver
            return
        Router.singleton()._register_binding(name, resolver)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]  # Route is the authorized caller

    def get(
        self,
        path: str,
        *,
        name: str | None = None,
        middleware: Sequence[MiddlewareRef] | None = None,
        controller: type | None = None,
        action: str | None = None,
        **extras: Any,
    ) -> Callable[[_H], _H]:
        return self._make_decorator(
            "GET",
            path,
            name=name,
            middleware=middleware,
            controller=controller,
            action=action,
            extras=extras,
        )

    def post(
        self,
        path: str,
        *,
        name: str | None = None,
        middleware: Sequence[MiddlewareRef] | None = None,
        controller: type | None = None,
        action: str | None = None,
        **extras: Any,
    ) -> Callable[[_H], _H]:
        return self._make_decorator(
            "POST",
            path,
            name=name,
            middleware=middleware,
            controller=controller,
            action=action,
            extras=extras,
        )

    def put(
        self,
        path: str,
        *,
        name: str | None = None,
        middleware: Sequence[MiddlewareRef] | None = None,
        controller: type | None = None,
        action: str | None = None,
        **extras: Any,
    ) -> Callable[[_H], _H]:
        return self._make_decorator(
            "PUT",
            path,
            name=name,
            middleware=middleware,
            controller=controller,
            action=action,
            extras=extras,
        )

    def patch(
        self,
        path: str,
        *,
        name: str | None = None,
        middleware: Sequence[MiddlewareRef] | None = None,
        controller: type | None = None,
        action: str | None = None,
        **extras: Any,
    ) -> Callable[[_H], _H]:
        return self._make_decorator(
            "PATCH",
            path,
            name=name,
            middleware=middleware,
            controller=controller,
            action=action,
            extras=extras,
        )

    def delete(
        self,
        path: str,
        *,
        name: str | None = None,
        middleware: Sequence[MiddlewareRef] | None = None,
        controller: type | None = None,
        action: str | None = None,
        **extras: Any,
    ) -> Callable[[_H], _H]:
        return self._make_decorator(
            "DELETE",
            path,
            name=name,
            middleware=middleware,
            controller=controller,
            action=action,
            extras=extras,
        )

    def head(
        self,
        path: str,
        *,
        name: str | None = None,
        middleware: Sequence[MiddlewareRef] | None = None,
        controller: type | None = None,
        action: str | None = None,
        **extras: Any,
    ) -> Callable[[_H], _H]:
        return self._make_decorator(
            "HEAD",
            path,
            name=name,
            middleware=middleware,
            controller=controller,
            action=action,
            extras=extras,
        )

    def options(
        self,
        path: str,
        *,
        name: str | None = None,
        middleware: Sequence[MiddlewareRef] | None = None,
        controller: type | None = None,
        action: str | None = None,
        **extras: Any,
    ) -> Callable[[_H], _H]:
        return self._make_decorator(
            "OPTIONS",
            path,
            name=name,
            middleware=middleware,
            controller=controller,
            action=action,
            extras=extras,
        )

    def resource(
        self,
        prefix: str,
        controller: type,
        *,
        parameter: str | None = None,
        middleware: Sequence[MiddlewareRef] | None = None,
    ) -> ResourceRegistration:
        """Register the seven canonical RESTful routes for ``controller``.

        ``Route.resource("/posts", PostController)`` mounts ``index``,
        ``create``, ``store``, ``show``, ``edit``, ``update``, and ``destroy``
        with conventional paths and names (``posts.index``, ``posts.show``,...).
        Member routes use a singular path parameter (``{post}`` for
        ``/posts``) so implicit model binding can resolve it. Override
        the parameter name with ``parameter=``. The returned
        :class:`ResourceRegistration` chains ``only``, ``except_``, and
        ``names`` to trim or rename the generated routes.
        """
        return ResourceRegistration(prefix, controller, parameter=parameter, middleware=middleware)

    def api_resource(
        self,
        prefix: str,
        controller: type,
        *,
        parameter: str | None = None,
        middleware: Sequence[MiddlewareRef] | None = None,
    ) -> ResourceRegistration:
        """Same as :meth:`resource`, but skip the HTML-form actions.

        ``create`` and ``edit`` are intended for server-rendered HTML forms;
        a JSON API never serves them. This convenience drops both.
        """
        actions = tuple(a for a in _RESOURCE_ACTIONS if a not in _HTML_ONLY_ACTIONS)
        return ResourceRegistration(
            prefix,
            controller,
            parameter=parameter,
            middleware=middleware,
            actions=actions,
        )

    @contextmanager
    def group(
        self,
        *,
        prefix: str = "",
        middleware: Sequence[MiddlewareRef] | None = None,
        name_prefix: str = "",
        tags: Sequence[str] | None = None,
    ) -> Any:
        frame = _GroupFrame(
            prefix=prefix,
            middleware=tuple(middleware or ()),
            name_prefix=name_prefix,
            tags=tuple(tags or ()),
        )
        token = _group_stack.set((*_group_stack.get(), frame))
        try:
            yield
        finally:
            _group_stack.reset(token)


Route: _RouteFacade = _RouteFacade()


# ───────────────────────── RouteServiceProvider ─────────────────────────


class RouteServiceProvider(ServiceProvider, ABC):
    """Subclass and implement ``map_routes(router)`` to register your routes."""

    @abstractmethod
    def map_routes(self, router: Router) -> None: ...

    async def boot(self) -> None:
        self.map_routes(Router.singleton())


_PARAM_RE = re.compile(r"\{(\w+)\}")


class RouteNotFoundError(KeyError):
    """Raised by route() when no named route matches the given name."""


class RoutingError(ValueError):
    """Raised on routing-layer misuse — missing params, missing APP_URL, etc.

    Subclasses ``ValueError`` so callers that handled the previous behaviour
    (``ValueError`` raised when a param was missing) still match.
    """


def _resolve_path(name: str, params: Mapping[str, Any]) -> str:
    """Substitute ``{name}`` placeholders in a named route's path."""
    for spec in Router.singleton().routes():
        if spec.name == name:

            def _replace(m: re.Match[str]) -> str:
                key = m.group(1)
                if key not in params:
                    raise RoutingError(f"route('{name}'): missing parameter '{key}'")
                return str(params[key])

            return _PARAM_RE.sub(_replace, spec.path)
    raise RouteNotFoundError(name)


def _app_url() -> str:
    """Read APP_URL from the environment, normalised with no trailing slash."""
    raw = os.environ.get("APP_URL")
    if not raw:
        msg = "APP_URL is not set; cannot build absolute URL."
        raise RoutingError(msg)
    return raw.rstrip("/")


def route(name: str, *, absolute: bool = False, **params: Any) -> str:
    """Generate a URL for the named route, substituting *params* into placeholders.

    With ``absolute=True``, prepends ``APP_URL`` to the result.

    Raises ``RouteNotFoundError`` when no registered route has the given name,
    ``RoutingError`` when a placeholder param is missing, and ``RoutingError``
    when ``absolute=True`` but ``APP_URL`` is unset.
    """
    path = _resolve_path(name, params)
    if absolute:
        return f"{_app_url()}{path}"
    return path


def url(path: str) -> str:
    """Resolve a relative path against ``APP_URL``.

    Idempotent for already-absolute URLs.
    """
    if path.startswith(("http://", "https://")):
        return path
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{_app_url()}{path}"


# ───────────────────────── URL signing ──────────────────────────────────────

_APP_KEY_PREFIX = "base64:"


def _app_key_bytes() -> bytes:
    """Return the raw HMAC key derived from ``APP_KEY``.

    Accepts ``base64:<b64>`` (Laravel default) and bare base64. Raises
    ``RoutingError`` when ``APP_KEY`` is missing.
    """
    raw = os.environ.get("APP_KEY")
    if not raw:
        msg = "APP_KEY is not set; cannot sign URLs."
        raise RoutingError(msg)
    payload = raw.removeprefix(_APP_KEY_PREFIX)
    return base64.b64decode(payload, validate=True)


def _normalise_expires(expires_at: datetime | int | None) -> int | None:
    """Convert an ``expires_at`` argument to a Unix timestamp int."""
    if expires_at is None:
        return None
    if isinstance(expires_at, int):
        return expires_at
    if expires_at.tzinfo is None:
        msg = "expires_at must be a timezone-aware datetime (received a naive one)."
        raise ValueError(msg)
    return int(expires_at.timestamp())


def _sign_message(message: str) -> str:
    """HMAC-SHA256 over *message*, base64url-encoded with no padding."""
    raw = hmac.new(_app_key_bytes(), message.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _signature_payload(base_url: str, query_without_signature: str) -> str:
    """Canonical payload signed for a URL — absolute `base_url?query`, `signature` stripped.

    Binds the signature to scheme+host+path so a link signed for one host can't be
    replayed against another host serving the same path (Laravel's hasValidSignature).
    """
    return f"{base_url}?{query_without_signature}" if query_without_signature else base_url


class _URLFacade:
    """Public ``URL`` facade — signed URL generation and verification."""

    def signed_route(
        self,
        name: str,
        *,
        expires_at: datetime | int | None = None,
        **params: Any,
    ) -> str:
        """Generate an absolute, HMAC-SHA256-signed URL for the named route.

        ``expires_at`` accepts a timezone-aware ``datetime`` or a Unix timestamp
        ``int``. Naive datetimes are rejected outright — silent local-timezone
        coercion is a footgun.
        """
        path = _resolve_path(name, params)
        expires = _normalise_expires(expires_at)
        query_pairs: list[tuple[str, str]] = []
        if expires is not None:
            query_pairs.append(("expires", str(expires)))
        query = urlencode(query_pairs)
        signature = _sign_message(_signature_payload(f"{_app_url()}{path}", query))
        query_pairs.append(("signature", signature))
        return f"{_app_url()}{path}?{urlencode(query_pairs)}"

    def has_valid_signature(self, request: Request) -> bool:
        """True iff the request URL bears a valid (and unexpired) HMAC signature."""
        query_params = request.query_params
        signature = query_params.get("signature")
        if not signature:
            return False

        expires_raw = query_params.get("expires")
        if expires_raw is not None:
            try:
                expires_ts = int(expires_raw)
            except TypeError, ValueError:
                return False
            if time.time() > expires_ts:
                return False

        # Rebuild the signed payload: absolute URL (scheme+host+path) + original
        # query minus `signature`. Host binding rejects cross-host replay.
        pairs = [(k, v) for k, v in query_params.multi_items() if k != "signature"]
        query_without_sig = urlencode(pairs)
        base_url = f"{request.url.scheme}://{request.url.netloc}{request.url.path}"
        expected = _sign_message(_signature_payload(base_url, query_without_sig))
        return constant_time_equals(expected, signature)


URL: _URLFacade = _URLFacade()


__all__ = [
    "URL",
    "ImplicitRouteModelBinder",
    "MethodControllerAdapter",
    "ResourceRegistration",
    "Route",
    "RouteNotFoundError",
    "RouteServiceProvider",
    "RouteSpec",
    "Router",
    "RoutingError",
    "route",
    "url",
]
