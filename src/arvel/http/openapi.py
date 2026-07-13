"""arvel.http.openapi — the OpenAPI document config: settings, render-plugin mapping, and
security-scheme construction.

Split out of ``HttpKernel`` (3.6: the kernel stays route-compile/dispatch; this module owns
everything OpenAPI-document-shaped) — a pure extraction, no behavior change. ``HttpKernel.build``
calls :func:`openapi_config` to get the ``litestar.openapi.OpenAPIConfig`` it feeds ``Litestar``.
"""

from __future__ import annotations

from typing import Any, Literal, cast

import msgspec

from arvel.kernel.settings import Settings

# friendly `.secure("bearer")` names -> the OpenAPI security-scheme component key they reference.
SECURITY_SCHEME_KEYS = {"bearer": "bearerAuth", "api_key": "apiKeyAuth"}


def _empty_dict_list() -> list[dict[str, Any]]:
    return []


def _empty_str_dict() -> dict[str, Any]:
    return {}


#: the 5 render plugins Litestar ships (``render_plugin`` maps each to its ``OpenAPIRenderPlugin``).
OpenApiUi = Literal["swagger", "redoc", "scalar", "rapidoc", "stoplight"]


class OpenApiSettings(Settings, forbid_unknown_fields=True):
    """Typed view over the ``openapi`` config section (DR-0016) — the full OpenAPI document config:
    identity (title/version/description/summary/terms), the ``path`` the schema + UI are served at, the
    ``ui`` renderer (swagger/redoc/scalar/rapidoc/stoplight — a closed set; an unknown name fails
    config validation instead of silently falling back), contact/license/servers/tags/external
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
    ui: OpenApiUi = "swagger"
    contact: dict[str, Any] | None = None
    license: dict[str, Any] | None = None
    servers: list[dict[str, Any]] = msgspec.field(default_factory=_empty_dict_list)
    tags: list[dict[str, Any]] = msgspec.field(default_factory=_empty_dict_list)
    external_docs: dict[str, Any] | None = None
    use_handler_docstrings: bool = True
    security: dict[str, Any] = msgspec.field(default_factory=_empty_str_dict)


def render_plugin(ui: str) -> Any:
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


def security_schemes(security: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Build OpenAPI security schemes from ``config('openapi').security`` — ``bearer`` (HTTP
    bearer/JWT → the 'Authorize' button), ``api_key`` (header/query key), and ``oidc``
    (OpenID Connect discovery → the IdP login, e.g. Keycloak). A truthy value defines the scheme;
    a ``dict`` customizes it (``format``/``description`` for bearer; ``name``/``in`` for api_key;
    ``openIdConnectUrl`` for oidc). ``default: true`` makes it required on every route (else routes
    opt in via ``.secure(...)``). Returns ``(schemes, default_requirements)``."""
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
    oidc = security.get("oidc")
    if oidc:
        opts = cast("dict[str, Any]", oidc) if isinstance(oidc, dict) else {}
        schemes["oidc"] = SecurityScheme(
            type="openIdConnect",
            open_id_connect_url=opts.get("openIdConnectUrl") or opts.get("url", ""),
            description=opts.get("description"),
        )
        if opts.get("default"):
            default_security.append({"oidc": []})
    return schemes, default_security


def openapi_config(json_plugin: Any = None) -> Any:
    """The OpenAPI document config — a typed view over the ``openapi`` config section
    (:class:`OpenApiSettings`, DR-0016): identity, the served ``path``, the ``ui`` renderer,
    contact/license/servers/tags/external-docs, and ``security`` schemes (the Swagger 'Authorize'
    button). Not Litestar's generic 'Litestar API' default. (Type-safe: msgspec-validated, not raw
    dict access.)

    ``json_plugin`` (arvel's ``JsonRenderPlugin`` subclass) renders ``/openapi.json`` — it injects the
    request bodies for pipeline-decoded bodies that Litestar's generator can't see. Passed by the
    kernel so both the served JSON and the UI (which fetches it) describe request bodies."""
    from litestar.openapi import OpenAPIConfig
    from litestar.openapi.spec import (
        Components,
        Contact,
        ExternalDocumentation,
        License,
        Server,
        Tag,
    )

    s = OpenApiSettings()
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
    plugins: list[Any] = []
    if json_plugin is not None:
        plugins.append(json_plugin)  # arvel's JSON renderer injects pipeline-decoded request bodies
    ui = render_plugin(s.ui)
    if ui is not None:
        plugins.append(ui)
    if plugins:
        kwargs["render_plugins"] = plugins
    schemes, default_security = security_schemes(s.security)
    if schemes:
        kwargs["components"] = Components(security_schemes=schemes)
        if default_security:  # require auth on every route unless one opts out
            kwargs["security"] = default_security
    return OpenAPIConfig(**kwargs)


__all__ = [
    "SECURITY_SCHEME_KEYS",
    "OpenApiSettings",
    "OpenApiUi",
    "openapi_config",
    "render_plugin",
    "security_schemes",
]
