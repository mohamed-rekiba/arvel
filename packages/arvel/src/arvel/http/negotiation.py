"""Content negotiation helpers."""

from __future__ import annotations


def wants_json(request: object) -> bool:
    """Returns True if the caller wants a JSON response.

    Heuristics, in order:
    1. URL path starts with ``/api`` (case-insensitive).
    2. ``Accept`` header mentions ``application/json``.
    3. ``X-Requested-With`` header equals ``XMLHttpRequest`` (XHR sentinel).
    """
    url = getattr(request, "url", None)
    path = getattr(url, "path", "") or ""
    if isinstance(path, str) and path.lower().startswith("/api"):
        return True

    raw_headers = getattr(request, "headers", {})
    headers = {str(k).lower(): str(v) for k, v in dict(raw_headers).items()}

    accept = headers.get("accept", "")
    if "application/json" in accept.lower():
        return True

    xhr = headers.get("x-requested-with", "")
    return xhr.lower() == "xmlhttprequest"
