"""Response helpers — convenience functions for common response types."""

from __future__ import annotations

from typing import Any

from starlette.responses import JSONResponse, RedirectResponse, Response


def json_response(
    data: Any,
    *,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Return a JSON response with the given data and status code."""
    return JSONResponse(content=data, status_code=status_code, headers=headers)


def redirect(url: str, *, status_code: int = 307) -> RedirectResponse:
    """Return a redirect response."""
    return RedirectResponse(url=url, status_code=status_code)


def no_content() -> Response:
    """Return a 204 No Content response."""
    return Response(status_code=204)
