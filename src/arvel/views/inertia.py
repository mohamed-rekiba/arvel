"""arvel.views.inertia — the Inertia protocol adapter (server-driven SPA).

A controller returns ``await inertia("Page", props)``. On an Inertia XHR (``X-Inertia``
header) arvel returns the page object as JSON; on a full page load it renders the Jinja boot
shell (the ``app`` template) with the page embedded, so the SPA hydrates client-side. The JS
lives in the separate ``frontend/`` workspace (doc 09) — Python only speaks the protocol.

Protocol pieces handled here: partial reloads (``X-Inertia-Partial-Data``/``-Component`` trim the
props to just those requested for a matching component) and asset versioning (the ``version`` is a
hash of the Vite manifest; a stale client version on a GET gets a 409 + ``X-Inertia-Location`` so it
hard-reloads the new assets).
"""

from __future__ import annotations

from typing import Any

from arvel.http.response import Response

_DEFAULT_MANIFEST = "public/build/manifest.json"
_version_cache: dict[str, str] = {}


def _hash_manifest(manifest_path: str) -> str:
    import hashlib
    from pathlib import Path

    try:
        digest = hashlib.sha256(Path(manifest_path).read_bytes()).hexdigest()
    except OSError:
        return "dev"  # no build yet (dev server) — a stable placeholder version
    return digest[:12]


async def _asset_version(manifest_path: str = _DEFAULT_MANIFEST) -> str:
    """Inertia asset version — a hash of the Vite manifest, so a new build invalidates a client's
    cached page version. Read off the event loop and cached per process (assets are stable within a
    deploy)."""
    cached = _version_cache.get(manifest_path)
    if cached is not None:
        return cached
    from anyio.to_thread import run_sync

    version = await run_sync(_hash_manifest, manifest_path)
    _version_cache[manifest_path] = version
    return version


def _partial_props(props: dict[str, Any], component: str, request: Any) -> dict[str, Any]:
    """For an Inertia partial reload — ``X-Inertia-Partial-Data`` naming the props to keep and
    ``X-Inertia-Partial-Component`` matching the current component — return just those props;
    otherwise every prop (a partial for a different component is a full page change)."""
    only = request.header("x-inertia-partial-data")
    if only and request.header("x-inertia-partial-component") == component:
        wanted = {key.strip() for key in only.split(",") if key.strip()}
        return {key: value for key, value in props.items() if key in wanted}
    return props


def inertia_page(
    component: str, props: dict[str, Any] | None, request: Any, version: str = "dev"
) -> dict[str, Any]:
    """The Inertia page object: component, props, current url, and asset version."""
    return {
        "component": component,
        "props": dict(props or {}),
        "url": request.path(),
        "version": version,
    }


async def inertia(
    component: str,
    props: dict[str, Any] | None = None,
    *,
    manifest_path: str = _DEFAULT_MANIFEST,
) -> Any:
    """Render an Inertia response: JSON for an ``X-Inertia`` request, else the HTML shell."""
    from arvel.http.request import current_request

    request = current_request.get()
    version = await _asset_version(manifest_path)

    if request.header("x-inertia"):
        # A GET whose cached asset version is stale can't safely swap props into an old bundle —
        # answer 409 + X-Inertia-Location so the client does a full reload of the new assets.
        if request.method().upper() == "GET":
            client_version = request.header("x-inertia-version")
            if client_version is not None and client_version != version:
                return Response("", status=409, headers={"X-Inertia-Location": request.path()})
        trimmed = _partial_props(dict(props or {}), component, request)
        page = inertia_page(component, trimmed, request, version)
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

    page = inertia_page(component, dict(props or {}), request, version)
    return await view("app", {"page": page}).to_response()
