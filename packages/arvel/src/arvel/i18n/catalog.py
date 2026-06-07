"""CatalogController — ETag-cached locale catalog endpoint.

SPAs fetch their i18n catalog at runtime via ``GET /i18n/{locale}``.
This keeps the backend authoritative: edit a string in
``resources/lang/{locale}.json``, restart the API, and every SPA refreshes
on its next conditional request without a build step.

Design decisions:

- Catalogs are read from flat ``{locales_dir}/{locale}.json`` files.
- An ``asyncio.Lock`` per locale prevents duplicate file reads under
  concurrent cold-cache requests.
- ETags are SHA-256 of the raw file bytes (first 16 hex chars) — stable
  across restarts when the file hasn't changed.
- Unknown locales return 404 without enumerating which locales exist
  (no information disclosure).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path
from typing import Final

from starlette.responses import Response

# BCP 47 primary subtag + optional subtags — rejects any path-traversal attempt.
_LOCALE_RE: Final[re.Pattern[str]] = re.compile(r"^[a-zA-Z]{2,8}(-[a-zA-Z0-9]{2,8})*$")

_CACHE_CONTROL: Final[str] = "public, max-age=3600, stale-while-revalidate=86400"
_VARY: Final[str] = "Accept-Encoding, If-None-Match"


class _CatalogEntry:
    __slots__ = ("etag", "raw_bytes")

    def __init__(self, raw_bytes: bytes, etag: str) -> None:
        self.raw_bytes = raw_bytes
        self.etag = etag


class CatalogController:
    """Serve locale catalogs from a flat directory with ETag revalidation.

    Instantiate once at application startup and register as a route handler:

        ctrl = CatalogController(locales_dir=Path("resources/lang"))
        router.get("/i18n/{locale}")(ctrl.serve)
    """

    def __init__(self, *, locales_dir: Path) -> None:
        self._dir = locales_dir
        self._cache: dict[str, _CatalogEntry] = {}
        # One asyncio.Lock per locale prevents redundant concurrent file reads.
        self._locks: dict[str, asyncio.Lock] = {}

    async def serve(
        self,
        locale: str,
        *,
        if_none_match: str | None = None,
    ) -> Response:
        """Return the catalog for ``locale``, or 304 when ETag matches.

        Returns 404 for any locale whose file is absent — never reveals
        which locales exist via error messages.
        """
        entry = await self._load(locale)
        if entry is None:
            return Response(
                content=b'{"error":"Locale not available."}',
                status_code=404,
                media_type="application/json",
            )

        etag_value = f'"{entry.etag}"'

        if if_none_match is not None and _etag_matches(if_none_match, entry.etag):
            return Response(
                status_code=304,
                headers={
                    "ETag": etag_value,
                    "Cache-Control": _CACHE_CONTROL,
                    "Content-Language": locale,
                    "Vary": _VARY,
                },
            )

        return Response(
            content=entry.raw_bytes,
            status_code=200,
            media_type="application/json",
            headers={
                "ETag": etag_value,
                "Cache-Control": _CACHE_CONTROL,
                "Content-Language": locale,
                "Vary": _VARY,
            },
        )

    async def _load(self, locale: str) -> _CatalogEntry | None:
        # Reject anything that isn't a valid BCP 47 tag — prevents path traversal.
        if not _LOCALE_RE.fullmatch(locale):
            return None

        if locale in self._cache:
            return self._cache[locale]

        # Get or create the per-locale lock before acquiring it.
        if locale not in self._locks:
            self._locks[locale] = asyncio.Lock()

        async with self._locks[locale]:
            # Double-check after acquiring the lock.
            if locale in self._cache:
                return self._cache[locale]

            entry = self._parse_catalog_file(self._dir / f"{locale}.json")
            if entry is not None:
                self._cache[locale] = entry
            return entry

    def _parse_catalog_file(self, path: Path) -> _CatalogEntry | None:
        if not path.is_file():
            return None
        raw_bytes = path.read_text(encoding="utf-8").encode("utf-8")
        try:
            parsed = json.loads(raw_bytes)
        except json.JSONDecodeError:
            return None
        if not isinstance(parsed, dict):
            return None
        etag = hashlib.sha256(raw_bytes).hexdigest()[:16]
        return _CatalogEntry(raw_bytes=raw_bytes, etag=etag)


def _etag_matches(header: str, etag: str) -> bool:
    """Compare an ``If-None-Match`` header against a single ETag (RFC 9110 §13.1.2)."""
    needle = etag.strip('"')
    for raw in header.split(","):
        candidate = raw.strip()
        if candidate == "*":
            return True
        if candidate.removeprefix("W/").strip('"') == needle:
            return True
    return False


__all__ = ["CatalogController"]
