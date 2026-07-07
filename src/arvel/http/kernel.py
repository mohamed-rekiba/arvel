"""arvel.http.HttpKernel — builds and serves a real ``litestar.Litestar`` app.

This is the G4-load-bearing piece: arvel's dynamic ``Route.get(path, handler)``
definitions are adapted onto Litestar route handlers (programmatic
``HTTPRouteHandler``), and OpenAPI is whatever **Litestar generates** from them.
Each request runs the two-tier middleware pipeline (global → group) before the
handler. Litestar is imported **lazily** in the serve path (``build``/``as_asgi``)
so ``import arvel`` and the T0 CLI stay light. *Lazy-import ≠ reimplement* (doc 00 §5b).

Grounded in knowledge/port/04-http-kernel-middleware.md (route-adaptation + pipeline).
"""

from __future__ import annotations

import inspect
import re
import typing
from typing import TYPE_CHECKING, Any, cast

from arvel.http import openapi
from arvel.http.request import Request, current_request
from arvel.http.response import Response

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

# one compiled route: (methods, path, handler, group, route_middleware, name, security,
# status_code, wheres, missing_callback, without_middleware)
_RouteEntry = tuple[
    list[str],
    str,
    Any,
    str | None,
    list[Any],
    str | None,
    list[str],
    int | None,
    dict[str, str],
    Any,
    list[Any],
]

_PARAM = re.compile(r"\{(\w+)(?::(\w+))?(\?)?\}")
# a `{name:<field>}` suffix outside this set is an arvel route-key field resolved by that column
_LITESTAR_CONVERTERS = frozenset(
    {"str", "int", "float", "uuid", "decimal", "date", "datetime", "time", "timedelta", "path"}
)


class _BindingMissing(Exception):
    """Internal control-flow signal: a route/model binding (explicit or implicit) didn't resolve.
    Caught in ``HttpKernel._dispatch`` so a route's ``.missing(callback)`` hook (if any) can render
    a custom response instead of the default 404."""


class HttpKernel:
    """Collects route definitions and compiles them into a Litestar application."""

    def __init__(self, app: Any = None) -> None:
        self.app = app
        # (methods, path, handler, group, route_middleware, name, security, status_code,
        #  wheres, missing_callback, without_middleware)
        self._routes: list[_RouteEntry] = []
        self.global_middleware: list[Any] = []
        self.groups: dict[str, list[Any]] = {"web": [], "api": []}
        self._aliases: dict[str, Any] = {}  # short name -> middleware class
        self.bindings: dict[str, Any] = {}  # route-param -> resolver (model/enum binding)

    # --- middleware group customization ---------------------------
    def append_to_group(self, group: str, *middleware: Any) -> HttpKernel:
        """Append middleware to a group (creating it if new)."""
        self.groups.setdefault(group, []).extend(middleware)
        return self

    def prepend_to_group(self, group: str, *middleware: Any) -> HttpKernel:
        """Prepend middleware to the front of a group."""
        self.groups.setdefault(group, [])[:0] = list(middleware)
        return self

    def middleware_group(self, name: str, stack: Sequence[Any]) -> HttpKernel:
        """Define (or replace) a named middleware group."""
        self.groups[name] = list(stack)
        return self

    def alias(self, mapping: dict[str, Any]) -> HttpKernel:
        """Register short aliases for middleware (usable in groups / route refs)."""
        self._aliases.update(mapping)
        return self

    def resolve_middleware(self, reference: Any) -> Any:
        """Resolve a middleware reference: an alias string -> its class; a ``throttle:<name>``
        string -> a:class:`~arvel.http.middleware.ThrottleRequests` bound to that named limiter;
        a generic ``alias:arg1,arg2`` string -> the registered alias class constructed with those
        (string) args, e.g. ``.alias({"cache.headers": CacheHeaders})`` + ``"cache.headers:60"`` ->
        ``CacheHeaders("60")``; else itself."""
        if isinstance(reference, str):
            name, sep, raw_args = reference.partition(":")
            if sep and name in self._aliases:
                target = self._aliases[name]
                return target(*raw_args.split(",")) if isinstance(target, type) else target
            if reference in self._aliases:
                return self._aliases[reference]
            if reference.startswith("throttle:"):
                from arvel.http.middleware import ThrottleRequests

                return ThrottleRequests(limiter_name=reference.removeprefix("throttle:"))
            return reference
        return reference

    def use_default_global(self) -> HttpKernel:
        """Ensure the framework's default GLOBAL middleware runs, in order: ``RequestContextMiddleware``
        (binds a request id into the log context — first, so every later log carries it), the
        maintenance-mode gate (``PreventRequestsDuringMaintenance`` → 503 while ``arvel down``),
        ``ValidatePostSize`` (413), ``ValidateHost`` (400), then ``LocaleMiddleware`` (sets the request
        locale) — all before session/CSRF/throttle. Idempotent. (M3: request-id + locale were defined
        but wired into no group; now they run for every request.)"""
        from arvel.http.maintenance import PreventRequestsDuringMaintenance
        from arvel.http.middleware import (
            LocaleMiddleware,
            RequestContextMiddleware,
            ValidateHost,
            ValidatePostSize,
        )
        from arvel.telemetry.middleware import TelemetryMiddleware

        defaults = (
            TelemetryMiddleware,  # outermost so its span covers everything below it
            RequestContextMiddleware,
            PreventRequestsDuringMaintenance,
            ValidatePostSize,
            ValidateHost,
            LocaleMiddleware,
        )
        for index, mw in enumerate(defaults):
            if mw not in self.global_middleware:
                self.global_middleware.insert(index, mw)
        return self

    def use_default_groups(self) -> HttpKernel:
        """Fill the default ``web`` (session, shared errors, CSRF) and ``api`` (throttle) groups —
        but only when a group hasn't already been customized, so an app's ``append_to_group`` /
        ``middleware_group`` done before serve is preserved (merge, not overwrite)."""
        from arvel.http.middleware import (
            SessionSettings,
            ShareErrorsFromSession,
            StartSession,
            ThrottleRequests,
            ValidateCsrfToken,
        )

        if not self.groups.get("web"):
            session_mw: Any = StartSession
            # redis sessions share the app's bound "cache" service, so they survive restarts
            if self.app is not None and self.app.bound("cache"):
                # from_source reads this app's own config section, not the global config()
                section = self.app.make("config").get("session", {})
                if SessionSettings.from_source(section).driver == "redis":
                    session_mw = StartSession(cache=self.app.make("cache"))
            # StartSession first (sets request.session); ShareErrorsFromSession reads it.
            self.groups["web"] = [session_mw, ShareErrorsFromSession, ValidateCsrfToken]
        if not self.groups.get("api"):
            self.groups["api"] = [ThrottleRequests]
        return self

    def add_route(
        self,
        methods: Sequence[str],
        path: str,
        handler: Any,
        group: str | None = None,
        middleware: Sequence[Any] | None = None,
        name: str | None = None,
        security: Sequence[str] | None = None,
        status_code: int | None = None,
        wheres: dict[str, str] | None = None,
        missing: Any | None = None,
        without_middleware: Sequence[Any] | None = None,
    ) -> None:
        self._routes.append(
            (
                [m.upper() for m in methods],
                path,
                handler,
                group,
                list(middleware or []),
                name,
                list(security or []),
                status_code,
                dict(wheres or {}),
                missing,
                list(without_middleware or []),
            )
        )

    def get(self, path: str, handler: Any, group: str | None = None) -> None:
        self.add_route(["GET"], path, handler, group)

    def post(self, path: str, handler: Any, group: str | None = None) -> None:
        self.add_route(["POST"], path, handler, group)

    def put(self, path: str, handler: Any, group: str | None = None) -> None:
        self.add_route(["PUT"], path, handler, group)

    def patch(self, path: str, handler: Any, group: str | None = None) -> None:
        self.add_route(["PATCH"], path, handler, group)

    def delete(self, path: str, handler: Any, group: str | None = None) -> None:
        self.add_route(["DELETE"], path, handler, group)

    def routes(self) -> list[_RouteEntry]:
        return list(self._routes)

    @staticmethod
    def _compile_path(path: str) -> tuple[list[str], dict[str, str]]:
        """Compile an arvel path to one or more Litestar paths + a map of
        ``param -> route-key field``. ``{id}`` → ``{id:str}``; ``{post:slug}`` → ``{post:str}``
        plus ``{"post": "slug"}`` (so implicit binding resolves Post by slug); a Litestar converter
        (``{x:path}``/``{x:int}``) passes through unchanged and records no field.

        A trailing run of optional params (``{x?}``) compiles to MULTIPLE Litestar paths — one per
        prefix length, via Litestar's own multi-path-per-handler support — so the route matches with
        or without those segments. The handler's own Python default applies when a segment is
        absent: Litestar simply never puts that name in ``path_params`` for the shorter path, so
        ``_dispatch`` never overrides the default (matches the convention that optional params must
        be the trailing run, same as the reference framework's ``{x?}``)."""
        fields: dict[str, str] = {}
        optional: list[str] = []

        def repl(m: re.Match[str]) -> str:
            name, suffix, opt = m.group(1), m.group(2), m.group(3)
            if opt:
                optional.append(name)
            if suffix is None:
                return "{" + name + ":str}"
            if suffix in _LITESTAR_CONVERTERS:
                return "{" + name + ":" + suffix + "}"
            fields[name] = suffix
            return "{" + name + ":str}"

        compiled = _PARAM.sub(repl, path)
        if not optional:
            return [compiled], fields
        paths = [compiled]
        shortened = compiled
        for name in reversed(optional):
            shortened = re.sub(r"/\{" + re.escape(name) + r":[^}]+\}", "", shortened)
            paths.append(shortened)
        return paths, fields

    def build(self, lifespan: Any = None) -> Any:
        """Compile the registered routes into a ``litestar.Litestar`` instance.

        ``lifespan`` (when given) is a Litestar lifespan callable that drives the arvel app's
        ``boot()``/``terminate()`` on ASGI startup/shutdown — see ``bootstrap.serve_lifespan``.
        """
        import litestar
        from litestar.handlers import HTTPRouteHandler

        from arvel.dates import Date
        from arvel.http.exceptions import HttpException, render_exception
        from arvel.validation import ValidationException

        # imported lazily so the http layer takes no hard dependency on the database module
        model_encoder: dict[Any, Callable[[Any], Any]] = {}
        extra_exception_handlers: dict[Any, Any] = {}
        try:
            from arvel.database.model import Model as _Model
            from arvel.database.model import ModelNotFound

            model_encoder = {_Model: lambda value: value.to_dict()}
            # find_or_fail/first_or_fail raise ModelNotFound; render it as 404 instead of a 500
            extra_exception_handlers = {ModelNotFound: render_exception}
        except Exception:  # pragma: no cover - database extra not installed
            model_encoder = {}

        self._warn_undefined_security()
        handlers = [
            self._make_handler(
                methods,
                path,
                handler,
                group,
                middleware,
                name,
                security,
                status_code,
                HTTPRouteHandler,
                wheres,
                missing,
                without_middleware,
            )
            for (
                methods,
                path,
                handler,
                group,
                middleware,
                name,
                security,
                status_code,
                wheres,
                missing,
                without_middleware,
            ) in self._routes
        ]
        litestar_app = litestar.Litestar(
            route_handlers=handlers,
            cors_config=self._cors_config(),
            openapi_config=openapi.openapi_config(),
            # serializes Date-typed model fields to ISO-8601 without a SerializationException
            type_encoders={Date: lambda value: value.to_iso(), **model_encoder},
            exception_handlers={
                ValidationException: render_exception,
                HttpException: render_exception,
                **extra_exception_handlers,
                # every other uncaught exception is reported then rendered, not left to Litestar's 500
                Exception: self._handle_uncaught,
            },
            after_response=self._persist_session,
            lifespan=[lifespan] if lifespan is not None else [],
        )
        return litestar_app

    @staticmethod
    async def _persist_session(request: Any) -> None:
        """Re-persist the session after the response (incl. flash/errors/old-input written by the
        redirect/exception paths, which run after the session middleware's pipeline pass). A no-op
        off the web group or on a serializer-less store where the earlier save already aliased."""
        record = getattr(getattr(request, "state", None), "arvel_session", None)
        if record is not None:
            middleware, arvel_request = record
            try:
                await middleware.persist(arvel_request)
            except Exception as exc:
                # runs after the response is sent — a transient store failure must be logged,
                # not raised into the ASGI teardown where it can't reach the client.
                from arvel.kernel.logging import LogManager

                LogManager().channel("http").error("session_persist_failed", error=repr(exc))

    def _warn_undefined_security(self) -> None:
        """Warn (at build) when a route's ``.secure(...)`` names a scheme that isn't defined in
        ``config('openapi').security`` — that would emit a dangling ``securitySchemes`` reference (a
        technically-invalid OpenAPI document). Non-fatal: the doc still serves."""
        secured = {
            scheme
            for *_, security, _status, _wheres, _missing, _without in self._routes
            for scheme in security
        }
        if not secured:
            return
        defined, _ = openapi.security_schemes(openapi.OpenApiSettings().security)
        from arvel.kernel.logging import LogManager

        log = LogManager().channel("http")
        for (
            _methods,
            path,
            _handler,
            _group,
            _middleware,
            name,
            security,
            _status,
            _wheres,
            _missing,
            _without,
        ) in self._routes:
            for scheme in security:
                if openapi.SECURITY_SCHEME_KEYS.get(scheme, scheme) not in defined:
                    log.warning(
                        "route_security_scheme_undefined", route=name or path, scheme=scheme
                    )

    def _handle_uncaught(self, request: Any, exc: BaseException) -> Any:
        """Report (5xx only) via the bound ``ExceptionHandler`` then render: a registered
        ``renderable`` callback wins, else content-negotiated default (E1).
        4xx (e.g. Litestar's NotFound) render through the same path but aren't reported as bugs."""
        from arvel.http.exceptions import render_exception

        handler = (
            self.app.make("exceptions")
            if self.app is not None and self.app.bound("exceptions")
            else None
        )
        status = int(getattr(exc, "status", None) or getattr(exc, "status_code", None) or 500)
        if status >= 500 and handler is not None:
            handler.report(exc)  # log unhandled (respects dont_report + reportables)
        if handler is not None and callable(getattr(handler, "try_render", None)):
            rendered = handler.try_render(request, exc)
            if rendered is not None:
                return self._to_litestar_response(rendered)
        return render_exception(request, exc, debug=self._debug())

    @staticmethod
    def _to_litestar_response(rendered: Any) -> Any:
        """An ``arvel.http.Response`` from a renderable becomes a litestar response; anything
        else (already a litestar Response, or a serializable body) passes through as-is."""
        from arvel.http.response import Response as ArvelResponse

        if isinstance(rendered, ArvelResponse):
            import litestar

            return litestar.Response(
                rendered.content, status_code=rendered.status, headers=rendered.headers
            )
        return rendered

    def _debug(self) -> bool:
        if self.app is None or not self.app.bound("config"):
            return False
        return bool(self.app.config("app.debug", False))

    def _cors_config(self) -> Any:
        """CORS handled by Litestar's own engine (preflight + headers + origin matching) —
        the ``HandleCors`` equivalent, not a hand-rolled middleware (doc 04: build on
        Litestar). Driven by ``config('cors')`` (Litestar ``CORSConfig`` keys: allow_origins,
        allow_methods, allow_headers, allow_credentials, allow_origin_regex, expose_headers,
        max_age). Returns ``None`` (CORS off) when unconfigured."""
        if self.app is None or not self.app.bound("config"):
            return None
        cfg = self.app.make("config").get("cors")
        if not isinstance(cfg, dict) or not cfg:
            return None
        from litestar.config.cors import CORSConfig

        allowed = set(CORSConfig.__dataclass_fields__)
        kwargs: dict[str, Any] = {
            k: v for k, v in cast("dict[str, Any]", cfg).items() if k in allowed
        }
        return CORSConfig(**kwargs)

    def as_asgi(self, lifespan: Any = None) -> Any:
        """The served ASGI application: the Litestar app (from:meth:`build`) wrapped in
        ``MethodOverride`` so a ``_method`` form field re-routes the request *before* Litestar matches
        by HTTP method. Non-HTTP scopes pass straight through to Litestar."""
        from arvel.http.middleware import MethodOverride

        return MethodOverride(self.build(lifespan))

    def openapi(self) -> dict[str, Any]:
        """The OpenAPI document Litestar generates from the registered routes (G4)."""
        schema: dict[str, Any] = self.build().openapi_schema.to_schema()
        return schema

    def _make_handler(
        self,
        methods: list[str],
        path: str,
        handler: Any,
        group: str | None,
        middleware: list[Any],
        name: str | None,
        security: list[str],
        status_code: int | None,
        route_handler: Any,
        wheres: dict[str, str],
        missing: Any,
        without_middleware: list[Any],
    ) -> Any:
        kernel = self
        litestar_paths, key_fields = self._compile_path(path)
        return_hint, body = self._handler_io(handler)
        body_name = body[0] if body is not None else None
        query_params = self._query_params(handler, litestar_paths[0], body_name)

        # Litestar reads `__signature__` below to know what to inject and document; split the
        # body back out of the injected kwargs and forward the rest to the handler as query args.
        async def adapter(request: Any, **injected: Any) -> Any:
            body_arg = (body_name, injected.pop(body_name)) if body_name is not None else None
            return await kernel._dispatch(
                handler,
                request,
                group,
                middleware,
                key_fields,
                body=body_arg,
                query=injected,
                wheres=wheres,
                missing=missing,
                without_middleware=without_middleware,
            )

        sig_params = [inspect.Parameter("request", inspect.Parameter.POSITIONAL_OR_KEYWORD)]
        annotations: dict[str, Any] = {"request": Any, "return": return_hint}
        if body is not None:
            sig_params.append(
                inspect.Parameter(body[0], inspect.Parameter.KEYWORD_ONLY, annotation=body[1])
            )
            annotations[body[0]] = body[1]
        for qname, qann, qdefault in query_params:
            sig_params.append(
                inspect.Parameter(
                    qname, inspect.Parameter.KEYWORD_ONLY, annotation=qann, default=qdefault
                )
            )
            annotations[qname] = qann
        adapter.__signature__ = inspect.Signature(sig_params, return_annotation=return_hint)  # type: ignore[attr-defined]
        adapter.__annotations__ = annotations

        # named from the route's name so the OpenAPI operationId/summary are clean, not a mangled fallback
        safe = re.sub(r"\W+", "_", f"{'_'.join(methods).lower()}{path}")
        adapter.__name__ = re.sub(r"\W+", "_", name) if name else f"arvel_{safe}"
        # carried over so Litestar's use_handler_docstrings can turn it into the OpenAPI description
        adapter.__doc__ = handler.__doc__
        # Litestar defaults DELETE to 204 (no body); arvel handlers may return one, so pin it to 200
        extra: dict[str, Any] = {}
        if status_code is not None:
            extra["status_code"] = status_code
        elif "DELETE" in methods:
            extra["status_code"] = 200
        if name:
            extra["operation_id"] = name
        if security:
            extra["security"] = [{openapi.SECURITY_SCHEME_KEYS.get(s, s): []} for s in security]
        route_path = litestar_paths[0] if len(litestar_paths) == 1 else litestar_paths
        return route_handler(path=route_path, http_method=methods, **extra)(adapter)

    @staticmethod
    def _handler_io(handler: Any) -> tuple[Any, tuple[str, Any] | None]:
        """Inspect a route handler for its OpenAPI I/O types: ``(return_hint, body)`` where ``body``
        is ``(param_name, struct_type)`` for the first ``msgspec.Struct``-typed parameter (→ a typed
        request body, distinct from model-binding params, which are ``Model`` subclasses) or ``None``.
        Best-effort — unresolved hints degrade to ``Any``/no-body, never raising."""
        import msgspec

        try:
            hints = typing.get_type_hints(handler)
        except Exception:
            hints = getattr(handler, "__annotations__", {}) or {}
        return_hint = hints.get("return", Any)
        try:
            params = inspect.signature(handler).parameters
        except ValueError, TypeError:
            return return_hint, None
        for pname in params:
            ann = hints.get(pname)
            if isinstance(ann, type) and issubclass(ann, msgspec.Struct):
                return return_hint, (pname, ann)
        return return_hint, None

    @staticmethod
    def _query_params(
        handler: Any, litestar_path: str, body_name: str | None
    ) -> list[tuple[str, Any, Any]]:
        """A handler's query parameters: every typed arg that isn't the request (first param), the
        body, or a path param. Returns ``(name, annotation, default)`` — exposed on the adapter so
        Litestar documents + injects them (``def index(request, q: str | None = None, page: int = 1)``).
        Best-effort; degrades to no query params on an unintrospectable handler."""
        path_names = set(re.findall(r"\{(\w+)", litestar_path))
        try:
            signature = inspect.signature(handler)
            hints = typing.get_type_hints(handler)
        except Exception:
            return []
        result: list[tuple[str, Any, Any]] = []
        for index, param in enumerate(signature.parameters.values()):
            if index == 0:
                continue
            if param.name == body_name or param.name in path_names:
                continue
            if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
                continue
            default = None if param.default is inspect.Parameter.empty else param.default
            result.append((param.name, hints.get(param.name, Any), default))
        return result

    async def _dispatch(
        self,
        handler: Any,
        litestar_request: Any,
        group: str | None = None,
        route_middleware: Sequence[Any] | None = None,
        key_fields: dict[str, str] | None = None,
        body: tuple[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        wheres: dict[str, str] | None = None,
        missing: Any = None,
        without_middleware: Sequence[Any] | None = None,
    ) -> Any:
        import contextlib

        from arvel.support import access_token, current_user

        request = Request(litestar_request)
        token = current_request.set(request)
        # reset every request so a stale current_user / access token can never leak across a
        # request boundary (the execution context is reused between requests)
        user_token = current_user.set(None)
        access_token_ctx = access_token.set(None)
        # a per-request container scope so `scoped` bindings share one instance for the request
        scope = self.app.scope() if self.app is not None else contextlib.nullcontext()
        try:
            async with scope:
                params = dict(litestar_request.path_params)
                self._apply_wheres(params, wheres or {})
                try:
                    await self._resolve_bindings(params)
                    await self._resolve_implicit_bindings(handler, params, key_fields or {})
                except _BindingMissing:
                    if missing is None:
                        self._not_found()
                    result = missing(request)
                    if inspect.isawaitable(result):
                        result = await result
                    return await self._to_response(result, request)
                if body is not None:
                    params[body[0]] = body[1]
                if query:
                    params.update(query)

                return await self._handle(
                    handler, request, params, group, route_middleware, without_middleware
                )
        finally:
            current_user.reset(user_token)
            access_token.reset(access_token_ctx)
            current_request.reset(token)

    def _apply_wheres(self, params: dict[str, Any], wheres: dict[str, str]) -> None:
        """``.where(param, pattern)`` constraints (routing 05): a captured segment that doesn't
        fullmatch its regex 404s — before bindings run, so a mismatched param never even reaches
        model resolution."""
        for name, pattern in wheres.items():
            value = params.get(name)
            if value is not None and re.fullmatch(pattern, str(value)) is None:
                self._not_found()

    async def _handle(
        self,
        handler: Any,
        request: Any,
        params: dict[str, Any],
        group: str | None,
        route_middleware: Sequence[Any] | None,
        without_middleware: Sequence[Any] | None = None,
    ) -> Any:
        async def destination(req: Any) -> Any:
            target = handler
            if isinstance(target, type):  # an invokable controller class — instantiate via the
                # container (DI for its constructor), same as `_make` does for middleware.
                target = self.app.make(target) if self.app is not None else target()
            if self.app is not None:
                result = self.app.call(target, request=req, **params)
            else:
                result = target(req, **params)
            if inspect.isawaitable(result):
                result = await result
            return result

        stack = [
            *self.global_middleware,
            *self.groups.get(group or "", []),
            *(route_middleware or []),
        ]
        if without_middleware:
            excluded = list(without_middleware)
            stack = [m for m in stack if not any(m == exc for exc in excluded)]
        # instantiate once so a terminable middleware shares state between handle() and terminate()
        instances = [self._make(self.resolve_middleware(m)) for m in stack]
        result = await self._run_pipeline(instances, request, destination)
        response = await self._to_response(result, request)
        await self._terminate(instances, request, response)
        return response

    async def _run_pipeline(self, instances: list[Any], request: Any, destination: Any) -> Any:
        async def run(index: int, req: Any) -> Any:
            if index >= len(instances):
                return await destination(req)
            handler = instances[index]

            def call_next(forwarded: Any) -> Any:
                return run(index + 1, forwarded)

            return await handler.handle(req, call_next)

        return await run(0, request)

    async def _terminate(self, instances: list[Any], request: Any, response: Any) -> None:
        """After the response is built, run each terminable middleware's
        ``terminate(request, response)`` hook (doc 04 — for session flush, logging, etc.)."""
        for instance in instances:
            hook = getattr(instance, "terminate", None)
            if callable(hook):
                outcome = hook(request, response)
                if inspect.isawaitable(outcome):
                    await outcome

    async def _resolve_bindings(self, params: dict[str, Any]) -> None:
        """Resolve *explicit* route-param bindings (``Route.model``/``bind_enum``) in
        place; raises ``_BindingMissing`` on a miss (``_dispatch`` turns that into 404, or the
        route's own ``.missing(callback)`` response)."""
        for name, resolver in self.bindings.items():
            if name not in params:
                continue
            resolved = resolver(params[name])
            if inspect.isawaitable(resolved):
                resolved = await resolved
            if resolved is None:
                raise _BindingMissing(name)
            params[name] = resolved

    async def _resolve_implicit_bindings(
        self, handler: Any, params: dict[str, Any], key_fields: dict[str, str] | None = None
    ) -> None:
        """Implicit route-model binding: a path param
        whose handler type hint is a model (duck-typed: has ``resolve_route_binding``)
        is resolved to that model by its route key; raises ``_BindingMissing`` on a miss (see
        :meth:`_resolve_bindings`). An inline ``{post:slug}`` route-key field (from ``key_fields``)
        overrides the model's default route key. Params already handled by an explicit binding are
        skipped. Duck-typing keeps the HTTP layer from importing the database layer.
        """
        key_fields = key_fields or {}
        try:
            hints = typing.get_type_hints(inspect.unwrap(handler))
        except Exception:  # unresolvable / forward-ref hints: skip implicit binding
            return
        for name in list(params):
            if name in self.bindings:  # an explicit binding already resolved this param
                continue
            annotation = hints.get(name)
            resolver = getattr(annotation, "resolve_route_binding", None)
            if resolver is None or not callable(resolver):
                continue
            resolved = resolver(params[name], key_fields.get(name))
            if inspect.isawaitable(resolved):
                resolved = await resolved
            if resolved is None:
                raise _BindingMissing(name)
            params[name] = resolved

    @staticmethod
    def _not_found() -> typing.NoReturn:
        from arvel.http.exceptions import HttpException
        from arvel.localization import trans

        raise HttpException(404, trans("http.not_found"))

    def _make(self, middleware_cls: Any) -> Any:
        # an already-built instance is used as-is; Container.make() expects a class/string abstract
        if not isinstance(middleware_cls, type):
            return middleware_cls
        return self.app.make(middleware_cls) if self.app is not None else middleware_cls()

    async def _to_response(self, result: Any, request: Any | None = None) -> Any:
        """Normalize any handler return into a Litestar ``Response`` (doc 04 §response
        normalization + HTTP-PARITY §2), so middleware/terminate see a uniform response object.
        The one conversion funnel for every value type a handler may return — extend here, don't
        add a second path."""
        import litestar

        if isinstance(result, litestar.Response):
            return cast("Any", result)
        if isinstance(result, Response):
            return self._apply_cookies(
                litestar.Response(
                    result.content, status_code=result.status, headers=result.headers
                ),
                result,
            )
        from arvel.http.redirect import Redirect

        if isinstance(result, Redirect):
            return await self._redirect_response(result, request)
        from arvel.http.response import FileDownload, StreamValue

        if isinstance(result, FileDownload):
            import mimetypes

            from litestar.response import File

            # Litestar's `File`/`Stream` resolve content-type from the *route handler's* declared
            # return annotation, not their own constructor arg — and every arvel adapter is typed
            # `Any` (dynamic handler I/O), so that resolution always lands on the JSON default.
            # Forcing it into `headers` sidesteps that resolution entirely.
            guessed = mimetypes.guess_type(str(result.name or result.path))[0]
            headers = {"content-type": guessed or "application/octet-stream", **result.headers}
            return cast(
                "Any",
                File(
                    path=result.path,
                    filename=result.name,
                    content_disposition_type="inline" if result.inline else "attachment",
                    headers=headers,
                ),
            )
        if isinstance(result, StreamValue):
            from litestar.response import Stream

            headers = {"content-type": result.media_type, **result.headers}
            return cast("Any", Stream(result.content, headers=headers))
        from arvel.pagination import AbstractPaginator

        if isinstance(result, AbstractPaginator):
            return cast("Any", litestar.Response(result.to_dict()))
        # a route handler returning a JsonResource/ResourceCollection (DB-MODEL §4) "just works" —
        # database sits below http in the layered DAG, so this downward import is legal.
        from arvel.database.resources import (
            JsonApiCollection,
            JsonApiResource,
            JsonResource,
            ResourceCollection,
        )

        if isinstance(result, (JsonApiResource, JsonApiCollection)):
            # the JSON:API media type is part of that spec's conformance, not a plain json response
            return cast(
                "Any",
                litestar.Response(
                    result.to_payload(request), media_type="application/vnd.api+json"
                ),
            )
        if isinstance(result, (JsonResource, ResourceCollection)):
            return cast("Any", litestar.Response(result.to_payload(request)))
        # no explicit status_code, so the route's method-aware default still applies (e.g. POST -> 201)
        return cast("Any", litestar.Response(result))

    @staticmethod
    def _apply_cookies(litestar_response: Any, response: Response) -> Any:
        """Apply a ``Response``'s queued cookies/expirations to the built Litestar response. A
        ``__Host-``-prefixed name gets ``path="/"``/no ``domain``/``secure=True`` forced — the full
        browser rule that prefix requires (``StartSession`` enforces the same for the session
        cookie). Without the forced ``Secure`` a ``__Host-`` cookie is silently rejected, so it
        overrides even an app whose ``session.secure`` is False; a non-prefixed cookie's unset
        ``secure`` defers to ``SessionSettings().secure``."""
        if not response.cookies and not response.forgotten_cookies:
            return litestar_response
        from arvel.http.middleware import SessionSettings

        default_secure = SessionSettings().secure
        for cookie in response.cookies:
            host_prefixed = cookie.name.startswith("__Host-")
            litestar_response.set_cookie(
                cookie.name,
                cookie.value,
                max_age=cookie.max_age,
                path="/" if host_prefixed else cookie.path,
                domain=None if host_prefixed else cookie.domain,
                secure=True
                if host_prefixed
                else (default_secure if cookie.secure is None else cookie.secure),
                httponly=cookie.http_only,
                samesite=cookie.same_site,
            )
        for name in response.forgotten_cookies:
            litestar_response.delete_cookie(name)
        return litestar_response

    @staticmethod
    async def _redirect_response(value: Any, request: Any) -> Any:
        """Convert a ``Redirect`` into a 302 (or its own ``status``), writing its flash/old-input/
        errors through the same session machinery ``ShareErrorsFromSession``/``render_exception``'s
        redirect-back path use — ``FlashBag`` and ``Request._flash_old_input`` — not a second
        implementation."""
        import litestar

        session = getattr(request, "session", None)
        if isinstance(session, dict):
            from arvel.http.flash import FlashBag

            bag = FlashBag(cast("dict[str, Any]", session))
            for key, flashed in value.flash_data.items():
                bag.flash(key, flashed)
            if value.errors is not None:
                bag.flash_errors(value.errors)
            if value.wants_input:
                content_type = request.header("content-type") or ""
                try:
                    data = (
                        await request.form()
                        if ("form" in content_type or "urlencoded" in content_type)
                        else await request.json()
                    )
                except Exception:  # unparseable/absent body → nothing to flash, not a 500
                    data = {}
                request._flash_old_input(data, except_=value.input_except)
        headers = {"Location": value.location or "/", **value.headers}
        return litestar.Response(None, status_code=value.status, headers=headers)
