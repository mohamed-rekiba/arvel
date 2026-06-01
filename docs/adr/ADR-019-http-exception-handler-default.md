# ADR-019: HttpExceptionHandler as Default Error Handler

**Status**: Accepted
**Date**: 2026-05-24
**Last reconciled**: 2026-06-01

## Context

`HttpServiceProvider` bound `ProblemDetailsHandler` as the default exception handler,
producing RFC 7807 `{type, title, status, detail}` envelopes. The documented and tested
contract is `{error: {code, message, details?}}`. Tests worked only because they manually
registered `HttpExceptionHandler`.

## Decision

`HttpServiceProvider` binds `HttpExceptionHandler` as the default. `ProblemDetailsHandler`
stays available as an opt-in import for projects that prefer RFC 7807.

## Consequences

- All HTTP error responses — including validation, auth, 404, and 500 — use one shape
- Frontend clients need only one error handler
- Projects that prefer RFC 7807 opt back in by binding `ProblemDetailsHandler` (which subclasses `HttpExceptionHandler`)

## Current implementation

- Default binding: `packages/arvel/src/arvel/providers/http_provider.py` binds `HttpExceptionHandler` (with the default foreign-exception translators).
- Opt-in RFC 7807: `packages/arvel/src/arvel/http/problem_details.py` (`ProblemDetailsHandler`, bound as a singleton override).
- Docs: `docs-fresh/http/exceptions.md`.
