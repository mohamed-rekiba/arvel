# ADR-013 — Route facade wraps FastAPI APIRouter, group state in a ContextVar stack

**Date**: 2026-05-17
**Status**: Accepted
**Last reconciled**: 2026-06-01
**Deciders**: Solution Architect (autonomous)
**Scope**: `arvel.routing`

---

## Context

Laravel's `Route::get(...)` / `Route::group(...)` are module-level facades over a global `Router` singleton. Group state (prefix, middleware, name prefix) stacks during the `group(...)` callback and unstacks on exit. On FastAPI we had three shapes: use `APIRouter` directly with no facade; build a router from scratch on Starlette; or wrap `APIRouter` with a thin facade that buffers route declarations at import time and flushes them onto the `FastAPI` instance at boot.

## Decision

**Wrap `APIRouter`.** `arvel.routing.Router` wraps `fastapi.APIRouter`. The `Route` facade is a module-level proxy to a single `Router`. Group state lives in a `contextvars.ContextVar` stack so nested `Route.group(...)` calls compose correctly and stay async/thread-safe. At boot, the router walks buffered routes and registers them on the `FastAPI` app, composing paths, middleware (per-route + per-group, run through the Arvel `Pipeline`), and names from the group stack.

## Why this shape

- Keeps all of FastAPI's machinery (OpenAPI generation, DI, response validation).
- Group composition stays clean — no global mutable dict, no thread-safety surprises.
- Gives Laravel DX without forcing users to think about routers.
- Leaves room for `Route.resource` / `Route.controller` later without changing the mounting.

Direct `APIRouter` was rejected because it doesn't compose group state through context managers and only offers `Depends`-style per-route middleware (not the `await call_next(request)` shape we want). Building from scratch on Starlette was rejected because it loses FastAPI's OpenAPI and ecosystem (constitution Article II.1: integrate, don't replace).

## Consequences

- Routes are buffered until boot registers them on the `FastAPI` app. Importing `bootstrap/app.py` is side-effect-free except for buffering — nothing hits the network.
- Route declaration is import-time only; declaring routes from a background thread without the right context lands them at the root group.
- Tests can reset the router to clear buffered routes between cases.

## Current implementation

- Code: `packages/arvel/src/arvel/routing/`, registered at boot by `arvel/providers/http_provider.py`.
- Docs: `docs-fresh/http/routing.md`.
