"""Application bootstrap for the e-commerce demo."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from arvel import Application
from arvel.auth.middleware.csrf_double_submit import _DEFAULT_EXEMPT
from arvel.http.middleware.security_headers import SecurityHeadersMiddleware
from arvel.i18n.middleware import SetLocaleMiddleware

_BASE_PATH = Path(__file__).resolve().parent.parent
if str(_BASE_PATH) not in sys.path:
    sys.path.insert(0, str(_BASE_PATH))

from app.http.controllers._responses import (
    ApiErrorOut,
)
from app.http.middleware import CsrfDoubleSubmitMiddleware

if TYPE_CHECKING:
    from fastapi import FastAPI


def create_application() -> Application:
    """Build the e-commerce application from the canonical layout."""
    routes_dir = _BASE_PATH / "routes"
    return (
        Application.configure(_BASE_PATH)
        .with_config_dir(_BASE_PATH / "config")
        .with_providers(_BASE_PATH / "bootstrap" / "providers.py")
        .with_routing(
            web=routes_dir / "web.py",
            api=routes_dir / "api.py",
            console=routes_dir / "console.py",
        )
        .create()
    )


def create_asgi(app: Application) -> FastAPI:
    """Produce the ASGI app with the e-commerce middleware stack."""
    asgi_app = app.into_asgi(
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )
    asgi_app.add_middleware(SetLocaleMiddleware)
    asgi_app.add_middleware(
        CsrfDoubleSubmitMiddleware,
        # /api/test/* is used by integration tests only; CSRF has no value there.
        exempt_paths=(*_DEFAULT_EXEMPT, "/api/test/"),
    )
    # Swagger UI and ReDoc load scripts/styles from cdn.jsdelivr.net and an
    # image from fastapi.tiangolo.com, plus an inline init script — all of
    # which the strict default-src 'self' policy blocks.  We apply a relaxed
    # policy only to those two paths; everything else keeps the tight default.
    _docs_csp = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
        "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
        "img-src 'self' data: https://fastapi.tiangolo.com; "
        "connect-src 'self' https://cdn.jsdelivr.net; "
        "frame-ancestors 'none'; "
        "form-action 'self'"
    )
    asgi_app.add_middleware(
        SecurityHeadersMiddleware,
        path_csp_overrides={
            "/api/docs": _docs_csp,
            "/api/redoc": _docs_csp,
        },
    )
    _patch_error_responses(asgi_app)
    return asgi_app


_TAG_RULES: list[tuple[str, str]] = [
    ("/api/auth/", "Auth"),
    ("/api/cart", "Cart"),
    ("/api/checkout", "Checkout"),
    ("/api/account/", "Account"),
    ("/api/i18n/", "I18n"),
    ("/api/admin/products", "Admin Products"),
    ("/api/admin/categories", "Admin Categories"),
    ("/api/admin/vendors", "Admin Vendors"),
    ("/api/admin/orders", "Admin Orders"),
    ("/api/admin/users", "Admin Users"),
    ("/api/admin/roles", "Admin Roles Permissions"),
    ("/api/admin/permissions", "Admin Roles Permissions"),
    ("/api/admin/translations", "Admin Translations"),
    ("/api/products", "Storefront"),
    ("/api/categories/", "Storefront"),
    ("/api/search", "Storefront"),
    ("/api/test/", "Testing"),
    ("/healthz", "System"),
]

_TAG_METADATA: list[dict[str, str]] = [
    {"name": "Auth", "description": "Login, registration, and current-user lookup."},
    {
        "name": "Storefront",
        "description": "Public product catalogue, category browsing, and search.",
    },
    {"name": "Cart", "description": "Shopping cart management."},
    {"name": "Checkout", "description": "Place orders from the active cart."},
    {"name": "Account", "description": "Authenticated user's own order history."},
    {"name": "I18n", "description": "Localised UI string bundles."},
    {"name": "Admin Products", "description": "Product CRUD, lifecycle, and media management."},
    {"name": "Admin Categories", "description": "Category CRUD and lifecycle."},
    {"name": "Admin Vendors", "description": "Vendor CRUD and lifecycle."},
    {"name": "Admin Orders", "description": "Order listing and status updates."},
    {"name": "Admin Users", "description": "User management, suspension, and role assignment."},
    {"name": "Admin Roles Permissions", "description": "Role and permission catalogue."},
    {"name": "Admin Translations", "description": "Translatable content catalogue."},
    {"name": "Testing", "description": "Internal endpoints used by integration tests only."},
    {"name": "System", "description": "Health checks and infrastructure probes."},
]


def _tag_for_path(path: str) -> str:
    for prefix, tag in _TAG_RULES:
        if path.startswith(prefix):
            return tag
    return "Other"


def _patch_error_responses(app: FastAPI) -> None:
    """Patch the generated OpenAPI schema with:

    - Our unified error envelope replacing FastAPI's HTTPValidationError
    - Common error codes (400/401/403/404/409/422/500) on every operation
    - BearerAuth security scheme and per-operation security requirement
    - Tag groups so Swagger UI organises endpoints into logical sections
    """
    _err_ref = {"$ref": "#/components/schemas/ApiErrorOut"}
    _err_content = {"application/json": {"schema": _err_ref}}
    _common_errors: dict[str, dict[str, Any]] = {
        "400": {"description": "Bad request", "content": _err_content},
        "401": {"description": "Unauthenticated", "content": _err_content},
        "403": {"description": "Forbidden", "content": _err_content},
        "404": {"description": "Not found", "content": _err_content},
        "409": {"description": "Conflict", "content": _err_content},
        "422": {"description": "Validation failed", "content": _err_content},
        "500": {"description": "Internal server error", "content": _err_content},
    }

    original_openapi = app.openapi  # type: ignore[attr-defined]

    def patched_openapi() -> dict[str, Any]:
        if app.openapi_schema:  # type: ignore[attr-defined]
            return app.openapi_schema  # type: ignore[attr-defined]

        schema: dict[str, Any] = original_openapi()

        # Inject ApiErrorOut and its nested schemas.
        # model_json_schema() nests sub-schemas under "$defs"; we need to lift
        # them into components/schemas so the $ref paths resolve correctly.
        components = schema.setdefault("components", {})
        model_schemas = components.setdefault("schemas", {})
        error_schema = ApiErrorOut.model_json_schema(
            mode="serialization",
            ref_template="#/components/schemas/{model}",
        )
        # Hoist nested $defs into the top-level schema registry.
        for name, defn in error_schema.pop("$defs", {}).items():
            model_schemas[name] = defn
        model_schemas["ApiErrorOut"] = error_schema
        # Remove FastAPI's built-in error schemas — they never appear in responses.
        model_schemas.pop("HTTPValidationError", None)
        model_schemas.pop("ValidationError", None)

        # Tag metadata drives the section order and descriptions in Swagger UI.
        schema["tags"] = _TAG_METADATA

        # Rewrite every operation: tags, error responses, and security.
        for path, path_item in schema.get("paths", {}).items():
            tag = _tag_for_path(path)
            for operation in path_item.values():
                if not isinstance(operation, dict):
                    continue
                operation.setdefault("tags", [tag])
                responses = operation.setdefault("responses", {})
                for code, resp in _common_errors.items():
                    responses[code] = resp
                operation.setdefault("security", [{"BearerAuth": []}])

        # Bearer security scheme — surfaces the "Authorize" button in Swagger UI.
        components.setdefault("securitySchemes", {})["BearerAuth"] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }

        app.openapi_schema = schema  # type: ignore[attr-defined]
        return schema

    app.openapi = patched_openapi  # type: ignore[method-assign]
