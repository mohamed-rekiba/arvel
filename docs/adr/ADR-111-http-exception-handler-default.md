# ADR-111: HttpExceptionHandler as Default Error Handler

**Status**: Accepted
**Date**: 2026-05-24

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
- Projects upgrading from `< 0.47` that explicitly relied on `ProblemDetailsHandler` must
  opt back in: `app.register_exception_handler(ProblemDetailsHandler())`
