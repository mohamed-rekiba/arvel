"""arvel.views.inertia — the Inertia protocol adapter (server-driven SPA).

A controller returns ``await inertia("Page", props)``. On an Inertia XHR (``X-Inertia``
header) arvel returns the page object as JSON; on a full page load it renders the Jinja boot
shell (the ``app`` template) with the page embedded, so the SPA hydrates client-side. The JS
lives in the separate ``frontend/`` workspace (doc 09) — Python only speaks the protocol.
"""

from __future__ import annotations

from typing import Any

from arvel.http.response import Response


def _asset_version() -> str:
    """Asset version for Inertia cache-busting (overridden when a manifest hash is wired)."""
    return "1"


def inertia_page(component: str, props: dict[str, Any] | None, request: Any) -> dict[str, Any]:
    """The Inertia page object: component, props, current url, and asset version."""
    return {
        "component": component,
        "props": dict(props or {}),
        "url": request.path(),
        "version": _asset_version(),
    }


async def inertia(component: str, props: dict[str, Any] | None = None) -> Any:
    """Render an Inertia response: JSON for an ``X-Inertia`` request, else the HTML shell."""
    from arvel.http.request import current_request

    request = current_request.get()
    page = inertia_page(component, props, request)
    if request.header("x-inertia"):
        import msgspec

        return Response(
            msgspec.json.encode(page).decode(),
            headers={
                "X-Inertia": "true",
                "Vary": "X-Inertia",
                "Content-Type": "application/json",
            },
        )
    from arvel.views import view

    return await view("app", {"page": page}).to_response()
