# ADR-121 — arvel-permission: UnauthorizedException as a typed exception

**Status**: Accepted
**Date**: 2026-05-24

## Context

Middleware currently returns an HTTP response directly from `__call__`. This means:
1. Callers can't differentiate "user unauthenticated" from "user lacks role" programmatically.
2. The HTTP response format is hardcoded and can't be customised without modifying middleware.
3. No exception is raised, so structured error logging hooks can't intercept auth failures.

## Decision

Add `UnauthorizedException(ArvelPermissionError)` with a `status_code: int` attribute.
Middleware raises it instead of returning a response directly. A fallback catch in middleware
converts it to HTTP if nothing handles it first.

## Consequences

- Positive: Callers can catch and handle auth failures (custom responses, audit logs).
- Positive: Framework exception handlers get a shot at formatting the error.
- Negative: Small breaking change if any code catches the raw HTTP response — acceptable because
  the fallback preserves identical HTTP output.
