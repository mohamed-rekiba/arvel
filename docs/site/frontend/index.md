# Frontend

Arvel is API-first. Your SPA or mobile app consumes JSON over HTTP, guided by an exported OpenAPI spec and a stable error envelope.

## Start here

**[Frontend Integration](integration.md)** — the full guide:

- Export and validate OpenAPI with `arvel openapi:export` / `openapi:validate`
- Generate typed clients (Orval, openapi-generator, …)
- Authenticate from browsers (cookies + bearer) vs native apps (secure storage)
- CORS, same-origin SPA hosting, Reverb realtime, push notification patterns

```bash
arvel openapi:export --output ../frontend/openapi.yaml
# → generate client → wire one request mutator for auth + errors
```

## See also

- [Authentication](../features/authentication.md#built-in-auth-routes) — built-in `/api/auth/*` endpoints.
- [Error Handling](../the-basics/error-handling.md#the-error-envelope) — parse one JSON shape for all failures.
- [E-commerce kit](../kits/ecommerce-kit.md) — Vue 3 + Orval reference frontend.
