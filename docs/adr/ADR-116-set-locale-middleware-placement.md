# ADR-116 — SetLocaleMiddleware placement in arvel.i18n.middleware

**Date**: 2026-05-23
**Status**: Accepted

## Context

`LocaleNegotiationMiddleware` exists in the fullstack Vue demo. It belongs in the framework.
Two placement options were considered:
- `arvel.http.middleware` (alongside SecurityHeadersMiddleware, DatabaseTransaction)
- `arvel.i18n.middleware` (alongside translator, helpers, loader)

## Decision

Place in `arvel.i18n.middleware`.

## Rationale

The middleware is semantically i18n infrastructure — it produces a locale value that
`arvel.i18n.t()` and `arvel.i18n.__()` consume. An app using i18n should import its locale
negotiation middleware from the same subsystem. The `arvel.http.middleware` package is for
generic HTTP infrastructure (transactions, throttle, auth, security headers) with no domain
coupling.

## Consequences

- `arvel.i18n.middleware.SetLocaleMiddleware` is the canonical import path
- Developers who use i18n find locale negotiation without needing to know about `arvel.http`
- The name follows Laravel's convention (`SetLocale` = sets state, not just negotiates)
