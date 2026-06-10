# The Basics

HTTP fundamentals: how requests reach your code, how input is validated, how responses are shaped, and how errors serialize. Most application code lives here.

## Recommended path

1. **[Routing](routing.md)** — `Route.get`, groups, named routes, model binding, resource routes.
2. **[Validation](validation.md)** — `FormRequest`, Pydantic payloads, rule strings, authorization.
3. **[API Resources](resources.md)** — `JsonResource`, collections, pagination wrappers.
4. **[Middleware](middleware.md)** — auth, throttle, CORS; route vs ASGI middleware.
5. **[Error Handling](error-handling.md)** — the `{ error: { code, message, details } }` envelope.
6. **[Controllers](controllers.md)** — optional; use when route files grow large.

```text
Request → middleware → FormRequest (validate) → handler → JsonResource → JSON
```

## What's in this section

| Page | Covers |
|---|---|
| [Routing](routing.md) | Verbs, groups, prefixes, signed URLs, `route:list` |
| [Controllers](controllers.md) | `Route.resource`, method injection, single-action controllers |
| [Validation](validation.md) | Two-layer validation, custom rules, 422 responses |
| [API Resources](resources.md) | Transformers, conditional fields, collections |
| [Middleware](middleware.md) | `Authenticate`, `Throttle`, `Cors`, custom middleware |
| [Error Handling](error-handling.md) | Typed exceptions, validation details, client contract |

## See also

- [Authentication](../features/authentication.md) and [Authorization](../features/authorization.md) for guards and gates.
- [Frontend Integration](../frontend/integration.md) for how SPAs consume the same error envelope and pagination shapes.
