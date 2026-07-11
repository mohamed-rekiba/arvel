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
from arvel.http.binding import BindingMissing, BindingResolver
from arvel.http.request import Request, current_request
from arvel.http.responder import to_litestar_response, to_response

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

# one compiled route: (methods, path, handler, group, route_middleware, name, security,
# status_code, wheres, missing_callback, without_middleware, domain, scope_bindings, trashed_all,
# trashed_params)
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
    str | None,
    bool,
    bool,
    frozenset[str],
]

_PARAM = re.compile(r"\{(\w+)(?::(\w+))?(\?)?\}")
# a `{name:<field>}` suffix outside this set is an arvel route-key field resolved by that column
_LITESTAR_CONVERTERS = frozenset(
    {"str", "int", "float", "uuid", "decimal", "date", "datetime", "time", "timedelta", "path"}
)
_DOMAIN_PARAM = re.compile(r"\\\{(\w+)\\\}")  # matches a `{name}` segment after re.escape


def _compile_domain(pattern: str) -> tuple[re.Pattern[str], frozenset[str]]:
    """``'{account}.example.com'`` -> a fullmatch regex over the request ``Host`` header (H1) +
    the param names it captures, compiled once at build. A ``{name}`` segment becomes a named
    capture group so a match also yields its value, merged into the handler params exactly like a
    path param."""
    escaped = re.escape(pattern)
    names = frozenset(_DOMAIN_PARAM.findall(escaped))
    source = _DOMAIN_PARAM.sub(lambda m: f"(?P<{m.group(1)}>[^.]+)", escaped)
    # hostnames are case-insensitive per DNS — a mixed-case literal Host must still match
    return re.compile(f"^{source}$", re.IGNORECASE), names


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
        # H12: the resolver holds `self.bindings` BY REFERENCE — routing mutates that dict after
        # construction (`kernel.bindings.update(...)` as routes register), so it must never be
        # rebuilt from a snapshot, only ever read/written through the same object.
        self._bindings = BindingResolver(self.bindings)
        # H5: middleware classes in the relative order they must run, regardless of which tier
        # (global/group/route) inserted them. Empty = no reordering (insertion order, unchanged).
        self.middleware_priority: list[Any] = []

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
        ``ValidatePostSize`` (413), ``ValidateHost`` (400), ``TrimStrings``/``ConvertEmptyStringsToNull``
        (H8 — global input normalization), then ``LocaleMiddleware`` (sets the request locale) — all
        before session/CSRF/throttle. Idempotent. (M3: request-id + locale were defined but wired
        into no group; now they run for every request.)"""
        from arvel.http.maintenance import PreventRequestsDuringMaintenance
        from arvel.http.middleware import (
            ConvertEmptyStringsToNull,
            LocaleMiddleware,
            RequestContextMiddleware,
            TrimStrings,
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
            TrimStrings,
            ConvertEmptyStringsToNull,
            LocaleMiddleware,
        )
        for index, mw in enumerate(defaults):
            if mw not in self.global_middleware:
                self.global_middleware.insert(index, mw)
        return self

    def use_default_groups(self) -> HttpKernel:
        """Fill the default ``web`` (cookie encryption, session, shared errors, CSRF) and ``api``
        (throttle) groups — but only when a group hasn't already been customized, so an app's
        ``append_to_group`` / ``middleware_group`` done before serve is preserved (merge, not
        overwrite)."""
        from arvel.http.middleware import (
            EncryptCookies,
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
            # EncryptCookies first (H7 — every cookie read/written below it goes through its
            # codec); StartSession next (sets request.session); ShareErrorsFromSession reads it.
            self.groups["web"] = [
                EncryptCookies,
                session_mw,
                ShareErrorsFromSession,
                ValidateCsrfToken,
            ]
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
        domain: str | None = None,
        scope_bindings: bool = False,
        trashed_all: bool = False,
        trashed_params: Sequence[str] | None = None,
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
                domain,
                scope_bindings,
                trashed_all,
                frozenset(trashed_params or ()),
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
        from arvel.validation import AuthorizationException, ValidationException

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
        # Litestar can't hold two handlers on the same method+path (an arbitrary constraint of the
        # underlying router, not something arvel needs) — domain routing (H1) puts two arvel routes
        # there deliberately, so entries sharing (methods, path) compile onto ONE Litestar handler
        # that picks among them by Host at request time. The overwhelmingly common case is a group
        # of exactly one, which costs nothing extra. Domain-specific candidates are tried before a
        # domain-less (matches-any-host) one at the same path, same "more specific wins" rule
        # `apply_to` already uses for fallback routes.
        grouped: dict[tuple[tuple[str, ...], str], list[_RouteEntry]] = {}
        for entry in self._routes:
            key = (tuple(entry[0]), entry[1])
            grouped.setdefault(key, []).append(entry)
        # merging only makes sense when the candidates differ by domain; two domain-less routes on
        # the same method+path would silently shadow each other — keep that a loud boot error, as it
        # was before H1's merge (an accidental duplicate should fail fast, not vanish at runtime).
        for (methods, path), candidates in grouped.items():
            if sum(entry[11] is None for entry in candidates) > 1:
                raise ValueError(
                    f"duplicate route {methods} {path!r} — two routes share a method+path with no "
                    "distinguishing domain; give them different paths or a domain= group"
                )
        handlers = [
            self._make_handler(
                sorted(candidates, key=lambda entry: entry[11] is None), HTTPRouteHandler
            )
            for candidates in grouped.values()
        ]
        litestar_app = litestar.Litestar(
            route_handlers=handlers,
            cors_config=self._cors_config(),
            openapi_config=openapi.openapi_config(),
            # serializes Date-typed model fields to ISO-8601 without a SerializationException
            type_encoders={Date: lambda value: value.to_iso(), **model_encoder},
            exception_handlers={
                ValidationException: render_exception,
                AuthorizationException: render_exception,
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
        secured = {scheme for entry in self._routes for scheme in entry[6]}
        if not secured:
            return
        defined, _ = openapi.security_schemes(openapi.OpenApiSettings().security)
        from arvel.kernel.logging import LogManager

        log = LogManager().channel("http")
        for entry in self._routes:
            path, name, security = entry[1], entry[5], entry[6]
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
                return to_litestar_response(rendered)
        return render_exception(request, exc, debug=self._debug())

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
        """The OpenAPI document Litestar generates from the registered routes (G4).

        Each operation's ``parameters`` list is sorted (by ``in`` then ``name``) so the document is
        byte-stable across runs — a codegen/CI drift gate diffs a fresh export against the committed
        one, and Litestar otherwise emits a multi-param route's parameters in set-iteration order."""
        schema: dict[str, Any] = self.build().openapi_schema.to_schema()
        paths: dict[str, Any] = schema.get("paths", {})
        for methods in paths.values():
            for operation in cast("dict[str, Any]", methods).values():
                if not isinstance(operation, dict):
                    continue
                params: Any = cast("dict[str, Any]", operation).get("parameters")
                if isinstance(params, list):
                    plist = cast("list[dict[str, Any]]", params)
                    plist.sort(key=lambda p: (str(p.get("in", "")), str(p.get("name", ""))))
        return schema

    def _make_handler(self, candidates: list[_RouteEntry], route_handler: Any) -> Any:
        """Compile one or more arvel routes that share a literal (methods, path) into ONE Litestar
        handler. Almost always a single candidate (the common case, no extra cost); more than one
        only happens for domain routing (H1), where the extra candidates differ solely by
        ``domain`` — at request time the adapter picks the first whose ``domain`` matches the
        ``Host`` header (``candidates`` is pre-sorted domain-specific-first) and dispatches through
        *that* candidate's own handler/bindings/middleware, injecting the domain's captured params
        alongside the path params."""
        kernel = self
        methods, path = candidates[0][0], candidates[0][1]
        litestar_paths, key_fields = self._compile_path(path)
        has_domain = any(entry[11] is not None for entry in candidates)
        compiled_domains = [
            _compile_domain(entry[11]) if entry[11] is not None else None for entry in candidates
        ]
        domain_regexes = [c[0] if c is not None else None for c in compiled_domains]
        # a domain-captured name (H1) is resolved from the Host header, not a Litestar path/query
        # param — excluded from query-param inference the same way a literal `{param}` is.
        domain_param_names = frozenset(
            name for c in compiled_domains if c is not None for name in c[1]
        )

        # OpenAPI/Litestar needs ONE signature for the shared handler: the body of the first
        # candidate that declares one, and the union of every candidate's query params (by name —
        # realistic domain variants are the same action for different tenants, so this is exact in
        # the common case and best-effort in the pathological one where they genuinely diverge).
        body: tuple[str, Any] | None = None
        return_hint: Any = Any
        query_by_name: dict[str, tuple[str, Any, Any]] = {}
        for index, entry in enumerate(candidates):
            hint, cand_body = self._handler_io(entry[2])
            if index == 0:
                return_hint = hint
            if body is None and cand_body is not None:
                body = cand_body
        body_name = body[0] if body is not None else None
        for entry in candidates:
            for qname, qann, qdefault in self._query_params(
                entry[2], litestar_paths[0], body_name, domain_param_names
            ):
                query_by_name.setdefault(qname, (qname, qann, qdefault))
        query_params = list(query_by_name.values())

        # Litestar reads `__signature__` below to know what to inject and document; split the
        # body back out of the injected kwargs and forward the rest to the handler as query args.
        async def adapter(request: Any, **injected: Any) -> Any:
            body_arg = (body_name, injected.pop(body_name)) if body_name is not None else None
            host = Request(request).host() if has_domain else None
            chosen: _RouteEntry | None = None
            domain_params: dict[str, Any] = {}
            for entry, regex in zip(candidates, domain_regexes, strict=True):
                if regex is None:
                    chosen = entry
                    break
                if host is not None:
                    match = regex.fullmatch(host)
                    if match is not None:
                        chosen = entry
                        domain_params = match.groupdict()
                        break
            if chosen is None:
                kernel._not_found()
            return await kernel._dispatch(
                chosen[2],
                request,
                chosen[3],
                chosen[4],
                key_fields,
                body=body_arg,
                query=injected,
                wheres=chosen[8],
                missing=chosen[9],
                without_middleware=chosen[10],
                name=chosen[5],
                domain_params=domain_params,
                scope_bindings=chosen[12],
                trashed_all=chosen[13],
                trashed_params=chosen[14],
            )

        sig_params = [inspect.Parameter("request", inspect.Parameter.POSITIONAL_OR_KEYWORD)]
        annotations: dict[str, Any] = {"request": Any, "return": return_hint}
        if body is not None:
            sig_params.append(
                inspect.Parameter(body[0], inspect.Parameter.KEYWORD_ONLY, annotation=body[1])
            )
            annotations[body[0]] = body[1]
        # Declare query params explicitly rather than letting Litestar infer them from a bare typed
        # default — the inferred style is deprecated upstream (warns per param, removed next major).
        from litestar.params import Parameter as _QueryParam

        # subscript Annotated through an Any ref: qann is a runtime value, not a static type
        annotate: Any = typing.Annotated
        for qname, qann, qdefault in query_params:
            annotated = annotate[qann, _QueryParam()]
            sig_params.append(
                inspect.Parameter(
                    qname, inspect.Parameter.KEYWORD_ONLY, annotation=annotated, default=qdefault
                )
            )
            annotations[qname] = annotated
        adapter.__signature__ = inspect.Signature(sig_params, return_annotation=return_hint)  # type: ignore[attr-defined]
        adapter.__annotations__ = annotations

        # named from the route's name so the OpenAPI operationId/summary are clean, not a mangled fallback
        name = candidates[0][5]
        safe = re.sub(r"\W+", "_", f"{'_'.join(methods).lower()}{path}")
        adapter.__name__ = re.sub(r"\W+", "_", name) if name else f"arvel_{safe}"
        # carried over so Litestar's use_handler_docstrings can turn it into the OpenAPI description
        adapter.__doc__ = candidates[0][2].__doc__
        # Litestar defaults DELETE to 204 (no body); arvel handlers may return one, so pin it to 200
        # ponytail: for merged domain candidates the Litestar-level signature — status_code,
        # security, name/__doc__, and the unioned body/query shape — is taken from the first
        # candidate. Exact for same-action-different-tenant domain routes (the real use case);
        # domain variants that need genuinely different OpenAPI metadata should use distinct paths.
        status_code, security = candidates[0][7], candidates[0][6]
        extra: dict[str, Any] = {}
        if status_code is not None:
            extra["status_code"] = status_code
        elif "DELETE" in methods:
            extra["status_code"] = 200
        if name:
            if len(methods) > 1:
                # a merged multi-method route (e.g. resource `update` = PUT+PATCH) shares one
                # handler; Litestar invokes a callable operation_id once per HTTP method, so this
                # disambiguates without splitting the handler — a plain string would collide.
                def _per_method_operation_id(
                    handler: Any, http_method: Any, path: Any, _base: str = name
                ) -> str:
                    return f"{_base}_{http_method.value.lower()}"

                extra["operation_id"] = _per_method_operation_id
            else:
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
        handler: Any,
        litestar_path: str,
        body_name: str | None,
        extra_excluded: frozenset[str] = frozenset(),
    ) -> list[tuple[str, Any, Any]]:
        """A handler's query parameters: every typed arg that isn't the request (first param), the
        body, a path param, or ``extra_excluded`` (a domain param, H1 — captured from the Host
        header, not a Litestar-level path/query param). Returns ``(name, annotation, default)`` —
        exposed on the adapter so Litestar documents + injects them
        (``def index(request, q: str | None = None, page: int = 1)``). Best-effort; degrades to no
        query params on an unintrospectable handler."""
        path_names = set(re.findall(r"\{(\w+)", litestar_path)) | extra_excluded
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
        name: str | None = None,
        domain_params: dict[str, Any] | None = None,
        scope_bindings: bool = False,
        trashed_all: bool = False,
        trashed_params: frozenset[str] = frozenset(),
    ) -> Any:
        import contextlib

        from arvel.http.request import RouteMatch
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
                # domain params (H1) first so a same-named path param — unlikely, but path wins —
                # takes precedence; both are captured segments, resolved the same way below.
                params = dict(domain_params or {})
                params.update(litestar_request.path_params)
                self._apply_wheres(params, wheres or {})
                # a missing bound model is not rendered here: doing so would 404 before the
                # pipeline (and Authenticate) ever runs, letting a guest tell an existing id from
                # a nonexistent one with zero credentials (DR-0054). The outcome is deferred to
                # `_handle`'s destination, which only renders it once auth/authz have passed.
                binding_missing = False
                try:
                    await self._bindings.resolve_explicit(params)
                    await self._bindings.resolve_implicit(
                        handler,
                        params,
                        key_fields or {},
                        scope_bindings=scope_bindings,
                        trashed_all=trashed_all,
                        trashed_params=trashed_params,
                    )
                except BindingMissing:
                    binding_missing = True
                # H4: the route's final name + resolved params, snapshotted before body/query (not
                # route params) are folded in below. On a miss these are the raw, unresolved
                # params — harmless, since the handler never runs on that path.
                request._route_match = RouteMatch(  # pyright: ignore[reportPrivateUsage]
                    name=name, params=dict(params)
                )
                if body is not None:
                    params[body[0]] = body[1]
                if query:
                    params.update(query)

                return await self._handle(
                    handler,
                    request,
                    params,
                    group,
                    route_middleware,
                    without_middleware,
                    binding_missing=binding_missing,
                    missing=missing,
                    body_param=body[0] if body is not None else None,
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
        binding_missing: bool = False,
        missing: Any = None,
        body_param: str | None = None,
    ) -> Any:
        async def destination(req: Any) -> Any:
            if binding_missing:
                # rendered here rather than in _dispatch so it runs *after* every middleware —
                # Authenticate/Authorize have already had their say by the time we get here.
                if missing is None:
                    self._not_found()
                result = missing(request)
                if inspect.isawaitable(result):
                    result = await result
                return result
            if body_param is not None:
                # A FormRequest-typed body runs its full lifecycle on injection (prepare →
                # rules() → passed_validation → authorize()), matching request.validate().
                # It runs here — after every middleware, like the binding-miss above — so a
                # validation 422 can never fire before Authenticate/Authorize (DR-0054's
                # oracle argument applies to validation too). prepare_for_validation sees the
                # structurally-decoded payload (msgspec has already parsed the body), not the
                # raw wire bytes.
                from arvel.validation import AuthorizationException, FormRequest

                injected = params.get(body_param)
                if isinstance(injected, FormRequest):
                    import msgspec

                    from arvel.localization import trans

                    parsed = type(injected).parse(msgspec.to_builtins(injected))
                    if not parsed.authorize():
                        # same exception + message as request.validate() — one 403 shape
                        raise AuthorizationException(trans("http.unauthorized"))
                    params[body_param] = parsed
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
        resolved = [self.resolve_middleware(m) for m in stack]
        instances = [self._make(m) for m in self._order_middleware(resolved)]
        result = await self._run_pipeline(instances, request, destination)
        response = await to_response(result, request)
        await self._terminate(instances, request, response)
        return response

    def _order_middleware(self, resolved: list[Any]) -> list[Any]:
        """H5: reorder ``resolved`` (already alias/throttle-resolved, global+group+route already
        concatenated) so any class named in ``middleware_priority`` runs in that relative order,
        regardless of which tier inserted it. Middleware absent from the list keeps its original
        relative order — a stable sort keyed by priority-index-or-last does exactly that. A no-op
        (returns ``resolved`` unchanged) when the priority list is empty, the default."""
        if not self.middleware_priority:
            return resolved

        def rank(mw: Any) -> int:
            cls = mw if isinstance(mw, type) else type(mw)
            try:
                return self.middleware_priority.index(cls)
            except ValueError:
                return len(self.middleware_priority)

        return sorted(resolved, key=rank)

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
