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

import msgspec

from arvel.http.request import Request, current_request
from arvel.http.response import Response
from arvel.kernel.settings import Settings

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

# Friendly ``.secure("bearer")`` / ``security.bearer`` names → the OpenAPI security-scheme component
# key they reference. Keeps app-facing config readable while the document uses canonical scheme ids.
_SECURITY_SCHEME_KEYS = {"bearer": "bearerAuth", "api_key": "apiKeyAuth"}


def _empty_dict_list() -> list[dict[str, Any]]:
    return []


def _empty_str_dict() -> dict[str, Any]:
    return {}


class OpenApiSettings(Settings, forbid_unknown_fields=True):
    """Typed view over the ``openapi`` config section (DR-0016) — the full OpenAPI document config:
    identity (title/version/description/summary/terms), the ``path`` the schema + UI are served at, the
    ``ui`` renderer (swagger/redoc/scalar/rapidoc/stoplight), contact/license/servers/tags/external
    docs, whether handler docstrings feed operation descriptions, and ``security`` schemes (e.g. a
    bearer/JWT scheme → the Swagger 'Authorize' button). Auto-loads + validates ``config('openapi')``;
    defaults when unset."""

    __config_key__ = "openapi"
    title: str = "arvel"
    version: str = "1.0.0"
    description: str | None = None
    summary: str | None = None
    terms_of_service: str | None = None
    path: str = "/schema"
    ui: str = "swagger"
    contact: dict[str, Any] | None = None
    license: dict[str, Any] | None = None
    servers: list[dict[str, Any]] = msgspec.field(default_factory=_empty_dict_list)
    tags: list[dict[str, Any]] = msgspec.field(default_factory=_empty_dict_list)
    external_docs: dict[str, Any] | None = None
    use_handler_docstrings: bool = True
    security: dict[str, Any] = msgspec.field(default_factory=_empty_str_dict)


_PARAM = re.compile(r"\{(\w+)(?::(\w+))?\}")
# Litestar's built-in path-param converters: a `{name:<conv>}` of these passes through to
# Litestar untouched. Any *other* `{name:<field>}` suffix is an arvel route-key field — the
# implicit model binding then resolves by that column (e.g. `{post:slug}` → Post by slug).
_LITESTAR_CONVERTERS = frozenset(
    {"str", "int", "float", "uuid", "decimal", "date", "datetime", "time", "timedelta", "path"}
)


class HttpKernel:
    """Collects route definitions and compiles them into a Litestar application."""

    def __init__(self, app: Any = None) -> None:
        self.app = app
        # (methods, path, handler, group, route_middleware, name, security, status_code)
        self._routes: list[
            tuple[list[str], str, Any, str | None, list[Any], str | None, list[str], int | None]
        ] = []
        self.global_middleware: list[Any] = []
        self.groups: dict[str, list[Any]] = {"web": [], "api": []}
        self._aliases: dict[str, Any] = {}  # short name -> middleware class
        self.bindings: dict[str, Any] = {}  # route-param -> resolver (model/enum binding)

    # --- middleware group customization (doc 04) ---------------------------
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
        """Resolve a middleware reference: an alias string -> its class; else itself."""
        if isinstance(reference, str):
            return self._aliases.get(reference, reference)
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
            # TelemetryMiddleware is outermost so its request span covers everything below it; it's a
            # no-op passthrough (no OpenTelemetry import) unless telemetry is enabled in config.
            TelemetryMiddleware,
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
            ShareErrorsFromSession,
            StartSession,
            ThrottleRequests,
            ValidateCsrfToken,
        )

        if not self.groups.get("web"):
            # StartSession first (sets request.session); ShareErrorsFromSession reads it.
            self.groups["web"] = [StartSession, ShareErrorsFromSession, ValidateCsrfToken]
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

    def routes(
        self,
    ) -> list[tuple[list[str], str, Any, str | None, list[Any], str | None, list[str], int | None]]:
        return list(self._routes)

    @staticmethod
    def _compile_path(path: str) -> tuple[str, dict[str, str]]:
        """Compile an arvel path to a Litestar path + a map of ``param -> route-key field``.
        ``{id}`` → ``{id:str}``; ``{post:slug}`` → ``{post:str}`` plus ``{"post": "slug"}`` (so
        implicit binding resolves Post by slug); a Litestar converter (``{x:path}``/``{x:int}``)
        passes through unchanged and records no field."""
        fields: dict[str, str] = {}

        def repl(m: re.Match[str]) -> str:
            name, suffix = m.group(1), m.group(2)
            if suffix is None:
                return "{" + name + ":str}"
            if suffix in _LITESTAR_CONVERTERS:
                return "{" + name + ":" + suffix + "}"
            fields[name] = suffix
            return "{" + name + ":str}"

        return _PARAM.sub(repl, path), fields

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

        # Serialize an arvel Model returned from a handler (or nested in a list/paginator) to its
        # to_dict() form — the Laravel ``return $user`` / ``return User::all()`` JSON path. Imported
        # lazily + via the contract base so the http layer takes no hard edge on the database module.
        model_encoder: dict[Any, Callable[[Any], Any]] = {}
        extra_exception_handlers: dict[Any, Any] = {}
        try:
            from arvel.database.model import Model as _Model
            from arvel.database.model import ModelNotFound

            model_encoder = {_Model: lambda value: value.to_dict()}
            # find_or_fail/first_or_fail raise ModelNotFound — render it as 404 (Laravel findOrFail
            # parity) rather than letting it fall to the generic 500 path. http→database is legal.
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
            )
            for methods, path, handler, group, middleware, name, security, status_code in self._routes
        ]
        litestar_app = litestar.Litestar(
            route_handlers=handlers,
            cors_config=self._cors_config(),
            openapi_config=self._openapi_config(),
            # Serialize the arvel Date value object to an ISO-8601 string in responses, so a handler
            # can return a model (or a paginator of models) whose date columns hydrate to Date — the
            # canonical Laravel ``return User::paginate()`` JSON path — without a SerializationException.
            # The Model encoder lets a handler return a model / collection of models directly.
            type_encoders={Date: lambda value: value.to_iso(), **model_encoder},
            exception_handlers={
                ValidationException: render_exception,
                HttpException: render_exception,
                **extra_exception_handlers,  # ModelNotFound → 404 (when the database module is present)
                # E1: every OTHER uncaught exception is reported through the bound ExceptionHandler
                # and rendered (content-negotiated) — not silently turned into Litestar's generic 500.
                Exception: self._handle_uncaught,
            },
            lifespan=[lifespan] if lifespan is not None else [],
        )
        return litestar_app

    def _openapi_config(self) -> Any:
        """The OpenAPI document config — a typed view over the ``openapi`` config section
        (:class:`OpenApiSettings`, DR-0016): identity, the served ``path``, the ``ui`` renderer,
        contact/license/servers/tags/external-docs, and ``security`` schemes (the Swagger 'Authorize'
        button). Not Litestar's generic 'Litestar API' default. (Type-safe: msgspec-validated, not raw
        dict access.)"""
        from litestar.openapi import OpenAPIConfig
        from litestar.openapi.spec import (
            Components,
            Contact,
            ExternalDocumentation,
            License,
            Server,
            Tag,
        )

        s = OpenApiSettings()  # auto-loads + validates config('openapi'); defaults when unset
        kwargs: dict[str, Any] = {
            "title": s.title,
            "version": s.version,
            "description": s.description,
            "summary": s.summary,
            "terms_of_service": s.terms_of_service,
            "path": s.path,
            "use_handler_docstrings": s.use_handler_docstrings,
        }
        if s.contact:
            kwargs["contact"] = Contact(**s.contact)
        if s.license:
            kwargs["license"] = License(**s.license)
        if s.servers:
            kwargs["servers"] = [Server(**srv) for srv in s.servers]
        if s.tags:
            kwargs["tags"] = [Tag(**tag) for tag in s.tags]
        if s.external_docs:
            kwargs["external_docs"] = ExternalDocumentation(**s.external_docs)
        plugin = self._render_plugin(s.ui)
        if plugin is not None:
            kwargs["render_plugins"] = [plugin]
        schemes, default_security = self._security_schemes(s.security)
        if schemes:
            kwargs["components"] = Components(security_schemes=schemes)
            if default_security:  # require auth on every route unless one opts out
                kwargs["security"] = default_security
        return OpenAPIConfig(**kwargs)

    @staticmethod
    def _render_plugin(ui: str) -> Any:
        """Map the configured ``ui`` to a Litestar render plugin (the API-docs UI served at ``path``).
        Default Swagger; ``None`` for an unknown name (Litestar falls back to its built-in UI)."""
        from litestar.openapi import plugins

        mapping = {
            "swagger": plugins.SwaggerRenderPlugin,
            "redoc": plugins.RedocRenderPlugin,
            "scalar": plugins.ScalarRenderPlugin,
            "rapidoc": plugins.RapidocRenderPlugin,
            "stoplight": plugins.StoplightRenderPlugin,
        }
        plugin = mapping.get(ui.lower())
        return plugin() if plugin is not None else None

    @staticmethod
    def _security_schemes(security: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Build OpenAPI security schemes from ``config('openapi').security`` — currently ``bearer``
        (HTTP bearer/JWT → the 'Authorize' button) and ``api_key`` (header/query key). A truthy value
        defines the scheme; a ``dict`` customizes it (``format``/``description`` for bearer; ``name``/
        ``in`` for api_key). ``default: true`` makes it required on every route (else routes opt in via
        ``.secure(...)``). Returns ``(schemes, default_requirements)``."""
        from litestar.openapi.spec import SecurityScheme

        schemes: dict[str, Any] = {}
        default_security: list[dict[str, Any]] = []
        bearer = security.get("bearer")
        if bearer:
            opts = cast("dict[str, Any]", bearer) if isinstance(bearer, dict) else {}
            schemes["bearerAuth"] = SecurityScheme(
                type="http",
                scheme="bearer",
                bearer_format=opts.get("format", "JWT"),
                description=opts.get("description"),
            )
            if opts.get("default"):
                default_security.append({"bearerAuth": []})
        api_key = security.get("api_key")
        if api_key:
            opts = cast("dict[str, Any]", api_key) if isinstance(api_key, dict) else {}
            schemes["apiKeyAuth"] = SecurityScheme(
                type="apiKey",
                name=opts.get("name", "X-API-Key"),
                security_scheme_in=opts.get("in", "header"),
                description=opts.get("description"),
            )
            if opts.get("default"):
                default_security.append({"apiKeyAuth": []})
        return schemes, default_security

    def _warn_undefined_security(self) -> None:
        """Warn (at build) when a route's ``.secure(...)`` names a scheme that isn't defined in
        ``config('openapi').security`` — that would emit a dangling ``securitySchemes`` reference (a
        technically-invalid OpenAPI document). Non-fatal: the doc still serves."""
        secured = {scheme for *_, security, _status in self._routes for scheme in security}
        if not secured:  # the common case — no per-route security, nothing to validate
            return
        defined, _ = self._security_schemes(OpenApiSettings().security)
        from arvel.kernel.logging import LogManager

        log = LogManager().channel("http")
        for _methods, path, _handler, _group, _middleware, name, security, _status in self._routes:
            for scheme in security:
                if _SECURITY_SCHEME_KEYS.get(scheme, scheme) not in defined:
                    log.warning(
                        "route_security_scheme_undefined", route=name or path, scheme=scheme
                    )

    def _handle_uncaught(self, request: Any, exc: BaseException) -> Any:
        """Report (5xx only) via the bound ``ExceptionHandler`` then render content-negotiated (E1).
        4xx (e.g. Litestar's NotFound) render through the same path but aren't reported as bugs."""
        from arvel.http.exceptions import render_exception

        status = int(getattr(exc, "status", None) or getattr(exc, "status_code", None) or 500)
        if status >= 500 and self.app is not None and self.app.bound("exceptions"):
            self.app.make("exceptions").report(exc)  # log unhandled (respects dont_report)
        return render_exception(request, exc, debug=self._debug())

    def _debug(self) -> bool:
        if self.app is None or not self.app.bound("config"):
            return False
        return bool(self.app.config("app.debug", False))

    def _cors_config(self) -> Any:
        """CORS handled by Litestar's own engine (preflight + headers + origin matching) —
        the Laravel ``HandleCors`` equivalent, not a hand-rolled middleware (doc 04: build on
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
        """The served ASGI application: the Litestar app (from :meth:`build`) wrapped in
        ``MethodOverride`` so a ``_method`` form field re-routes the request *before* Litestar matches
        by HTTP method (Laravel @method). Non-HTTP scopes pass straight through to Litestar."""
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
    ) -> Any:
        kernel = self
        litestar_path, key_fields = self._compile_path(path)
        return_hint, body = self._handler_io(handler)

        adapter: Any
        if body is not None:
            body_name, body_type = body

            # the handler declares a typed request body (a msgspec.Struct param) — expose it to
            # Litestar as `data` so the body is parsed/validated AND a request schema is generated,
            # then forward it to the handler under its own param name.
            async def adapter_with_body(request: Any, data: Any) -> Any:
                return await kernel._dispatch(
                    handler, request, group, middleware, key_fields, body=(body_name, data)
                )

            adapter = adapter_with_body
            adapter.__annotations__ = {"request": Any, "data": body_type, "return": return_hint}
        else:

            async def adapter_plain(request: Any) -> Any:
                return await kernel._dispatch(handler, request, group, middleware, key_fields)

            adapter = adapter_plain
            adapter.__annotations__ = {"request": Any, "return": return_hint}

        # Name the adapter from the route's name when given (e.g. "home"/"api.health" →
        # home / api_health) so the OpenAPI operationId + summary are clean — not the mangled
        # method+path fallback ("ArvelGetApiHealth"). Fall back to a unique method+path id.
        safe = re.sub(r"\W+", "_", f"{'_'.join(methods).lower()}{path}")
        adapter.__name__ = re.sub(r"\W+", "_", name) if name else f"arvel_{safe}"
        # Carry the original handler's docstring onto the synthetic adapter so Litestar's
        # use_handler_docstrings turns it into the OpenAPI operation description (otherwise the
        # adapter is blank and the operation has only a name-derived summary).
        adapter.__doc__ = handler.__doc__
        # DELETE defaults to 204 (no body) in Litestar; arvel handlers may return a
        # body, so pin DELETE routes to 200. GET/POST keep Litestar's 200/201 defaults.
        # explicit per-route status wins; else DELETE → 200 (arvel handlers may return a body);
        # else Litestar's per-method default (GET 200 / POST 201).
        extra: dict[str, Any] = {}
        if status_code is not None:
            extra["status_code"] = status_code
        elif "DELETE" in methods:
            extra["status_code"] = 200
        if name:  # explicit operationId = the route name (else Litestar doubles the path prefix)
            extra["operation_id"] = name
        if security:  # this route requires auth → mark it (the Swagger lock + 'Authorize' use)
            extra["security"] = [{_SECURITY_SCHEME_KEYS.get(s, s): []} for s in security]
        return route_handler(path=litestar_path, http_method=methods, **extra)(adapter)

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

    async def _dispatch(
        self,
        handler: Any,
        litestar_request: Any,
        group: str | None = None,
        route_middleware: Sequence[Any] | None = None,
        key_fields: dict[str, str] | None = None,
        body: tuple[str, Any] | None = None,
    ) -> Any:
        import contextlib

        from arvel.support import current_user

        request = Request(litestar_request)
        token = current_request.set(request)
        # Per-request identity baseline: guarantees current_user never survives a request boundary,
        # so route-protection middleware fail closed even if AuthenticateMiddleware isn't wired or a
        # handler sets the user without resetting (e.g. AuthManager.login()). Defence-in-depth.
        user_token = current_user.set(None)
        # S1: open a per-request container scope so `scoped` bindings share one instance for the
        # duration of the request (and are released at the end), not rebuilt per make().
        scope = self.app.scope() if self.app is not None else contextlib.nullcontext()
        try:
            async with scope:
                params = dict(litestar_request.path_params)
                await self._resolve_bindings(params)
                await self._resolve_implicit_bindings(handler, params, key_fields or {})
                if body is not None:  # typed request body → pass under the handler's param name
                    params[body[0]] = body[1]

                return await self._handle(handler, request, params, group, route_middleware)
        finally:
            current_user.reset(user_token)
            current_request.reset(token)

    async def _handle(
        self,
        handler: Any,
        request: Any,
        params: dict[str, Any],
        group: str | None,
        route_middleware: Sequence[Any] | None,
    ) -> Any:
        async def destination(req: Any) -> Any:
            if self.app is not None:
                result = self.app.call(handler, request=req, **params)
            else:
                result = handler(req, **params)
            if inspect.isawaitable(result):
                result = await result
            return result

        # Instantiate each middleware once so a terminable one shares state between its
        # handle() (request in) and terminate() (response out). Order: global → group → route.
        instances = [
            self._make(self.resolve_middleware(m))
            for m in (
                *self.global_middleware,
                *self.groups.get(group or "", []),
                *(route_middleware or []),
            )
        ]
        result = await self._run_pipeline(instances, request, destination)
        response = self._to_response(result)
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
        place; 404 on a miss."""
        for name, resolver in self.bindings.items():
            if name not in params:
                continue
            resolved = resolver(params[name])
            if inspect.isawaitable(resolved):
                resolved = await resolved
            if resolved is None:
                self._not_found()
            params[name] = resolved

    async def _resolve_implicit_bindings(
        self, handler: Any, params: dict[str, Any], key_fields: dict[str, str] | None = None
    ) -> None:
        """Implicit route-model binding (Laravel ``SubstituteBindings``): a path param
        whose handler type hint is a model (duck-typed: has ``resolve_route_binding``)
        is resolved to that model by its route key; 404 on a miss. An inline ``{post:slug}``
        route-key field (from ``key_fields``) overrides the model's default route key. Params
        already handled by an explicit binding are skipped. Duck-typing keeps the HTTP layer
        from importing the database layer.
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
                self._not_found()
            params[name] = resolved

    @staticmethod
    def _not_found() -> None:
        from arvel.localization import trans
        from arvel.validation import ValidationException

        raise ValidationException(trans("http.not_found"), status=404)

    def _make(self, middleware_cls: Any) -> Any:
        return self.app.make(middleware_cls) if self.app is not None else middleware_cls()

    def _to_response(self, result: Any) -> Any:
        """Normalize any handler return into a Litestar ``Response`` (doc 04 §response
        normalization), so middleware/terminate see a uniform response object."""
        import litestar

        if isinstance(result, litestar.Response):
            return cast("Any", result)
        if isinstance(result, Response):  # arvel Response → carry status/headers across
            return litestar.Response(
                result.content, status_code=result.status, headers=result.headers
            )
        from arvel.pagination import AbstractPaginator

        if isinstance(result, AbstractPaginator):  # paginator → Laravel JSON shape (auto-serialize)
            return cast("Any", litestar.Response(result.to_dict()))
        # plain dict/list/str/bytes/None → a Litestar Response; no explicit status_code so the
        # route's method-aware default still applies (e.g. POST → 201), and Litestar infers the
        # media type from the content.
        return cast("Any", litestar.Response(result))
