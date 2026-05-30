# ADR-101: `CatalogController` — ETag + per-locale lock

**Status**: Accepted
**Date**: 2026-05-24

## Context

SPAs fetch their i18n catalog at runtime. The fullstack Vue demo implemented this as a
local `I18nController`. Every project building a Vue/React SPA on arvel needs this pattern.

## Decision

Ship `CatalogController` in `arvel.i18n.catalog`. Auto-register `GET /api/i18n/{locale}`
via `LangServiceProvider` when `LangConfig.catalog_endpoint = True` (opt-in, default False).

Design choices:
1. **ETags** are SHA-256 of raw file bytes (first 16 hex chars). Stable across restarts.
2. **Per-locale `asyncio.Lock`** prevents duplicate file reads on cold-cache concurrent hits.
3. **Locale validation** via `^[a-zA-Z]{2,8}(-[a-zA-Z0-9]{2,8})*$` regex. Path traversal
   rejected at the regex gate before any filesystem access.
4. **404 for unknown locales** with no enumeration of supported locales in the error body.
5. **Boot-time JSON validation** — invalid catalog files raise `RuntimeError` at provider boot,
   not silently at first request.
6. **Cache-Control headers**: `public, max-age=3600, stale-while-revalidate=86400` and
   `Vary: Accept-Encoding, If-None-Match`.

## Rationale

- **Opt-in**: Not every arvel app has a SPA frontend. Default `False` keeps the package
  non-invasive for API-only projects.
- **Per-locale lock vs global lock**: A global lock would serialize all concurrent cold
  reads. Per-locale locks allow `en` and `es` cold reads to proceed in parallel.
- **SHA-256 ETag vs timestamp**: File mtime can change without content change (e.g. `touch`,
  volume mount on Docker restart). SHA-256 is content-derived and stable.
- **RuntimeError at boot**: Silently serving a broken catalog until the first SPA request
  causes a harder-to-diagnose failure. Fail fast during provider boot instead.

## Rejected Alternative

A per-request filesystem read with no caching — simpler but defeats the purpose of an
ETag-capable endpoint on a catalog that changes only on deploy.
