# Frontend Integration

<a name="introduction"></a>
## Introduction

Arvel is an API-first framework. Your handlers return [API resources](../the-basics/resources.md), your errors serialize to one [envelope](../the-basics/error-handling.md#the-error-envelope), and the whole surface is described by an OpenAPI document the framework generates for you. That makes it a natural backend for a separate-origin SPA (Vue, React, Svelte) or a native mobile app (Swift, Kotlin, Flutter).

This guide covers the contract between Arvel and those clients: how to generate a typed client from the spec, how to authenticate from a browser versus a phone, how CORS and realtime fit in, and the response shapes every client should expect.

<a name="quick-start"></a>
### Quick start

```bash
# 1. Export the contract from the backend
arvel openapi:export --output ../frontend/openapi.yaml

# 2. Generate a typed client (Orval example — see below)
cd ../frontend && npm run api:generate

# 3. Route every generated call through one mutator for auth + errors
#    frontend/src/lib/api.ts — attach Bearer token, parse { error: { ... } }
```

```ts
// Minimal fetch wrapper — every Orval call goes through this
const token = localStorage.getItem('access_token')
const res = await fetch(url, {
  headers: token ? { Authorization: `Bearer ${token}` } : {},
})
if (!res.ok) {
  const body = await res.json()
  throw new Error(body?.error?.message ?? res.statusText)
}
```

| Step | Doc section |
|---|---|
| Export + validate spec | [The OpenAPI contract](#the-openapi-contract) |
| Generate hooks / SDK | [Generating a typed client](#generating-a-typed-client) |
| Login + refresh | [Authentication](#authentication) |
| SPA on another origin | [CORS](#cors) |
| Same-origin deploy | [Serving a built SPA](#serving-a-spa) |
| Live updates | [Realtime](#realtime) |

> [!NOTE]
> The [e-commerce kit](../kits/ecommerce-kit.md) ships a real Vue 3 + Orval frontend wired against an Arvel backend. Every snippet below is drawn from that setup — clone it if you want a working reference.

<a name="the-openapi-contract"></a>
## The OpenAPI Contract

Arvel builds an OpenAPI 3.x document from your routes, [form requests](../the-basics/validation.md), and [resources](../the-basics/resources.md). Two CLI commands produce and check it:

```bash
# Write the spec to docs/api/openapi.yaml (the default path)
arvel openapi:export

# Write directly to a sibling project — relative paths resolve against the
# current working directory, absolute paths are accepted, status goes to stderr.
arvel openapi:export --output ../frontend/openapi.yaml --format yaml

# Or stream it to stdout for a build pipeline (--output - is the POSIX-style alias).
arvel openapi:export --format yaml --stdout > frontend/openapi.yaml
arvel openapi:export --output - --format yaml | tee frontend/openapi.yaml

# Validate the live app's spec against the OpenAPI 3.x schema
arvel openapi:validate

# Or validate a spec file you already exported
arvel openapi:validate --spec frontend/openapi.yaml
```

`openapi:validate` needs the `openapi-spec-validator` package — install the `openapi` extra (`uv add "arvel[openapi]"`) if it isn't already present. Wire `openapi:validate` into CI so a route change that breaks the contract fails the build before it reaches a client.

> [!TIP]
> The exported spec is the single source of truth. Don't hand-write client types — generate them from this file so the client and server can never drift.

<a name="generating-a-typed-client"></a>
## Generating a Typed Client

Any OpenAPI generator works against the exported spec. The kit uses [Orval](https://orval.dev), which produces typed functions plus framework-specific hooks. Its config mirrors the kit's `orval.config.ts`:

```ts
// frontend/orval.config.ts
import { defineConfig } from 'orval'

export default defineConfig({
  api: {
    input: { target: './openapi.yaml' },
    output: {
      mode: 'tags-split',          // one file per OpenAPI tag
      target: './src/api/index.ts',
      schemas: './src/api/schemas',
      client: 'vue-query',         // or 'react-query', 'angular', 'svelte-query', 'axios'
      prettier: true,
      clean: true,
      override: {
        mutator: { path: './src/lib/api.ts', name: 'request' },
      },
    },
  },
})
```

> [!NOTE]
> The `client` option selects the framework and data-fetching layer Orval generates for. See Orval's [`client` reference](https://orval.dev/docs/reference/configuration/output/) for the full list — `angular`, `angular-query`, `react-query`, `vue-query`, `svelte-query`, `swr`, `axios`, `fetch`, and more — and the per-framework guides (e.g. [Angular](https://orval.dev/docs/guides/angular/)) for setup details.

The `mutator` is the key piece: every generated call routes through your `request` function, so auth headers, base URLs, and error normalization live in one place instead of being baked into generated code:

```ts
// frontend/src/lib/api.ts
interface RequestConfig {
  url: string
  method: string
  headers?: Record<string, string>
  data?: unknown
  params?: Record<string, unknown>
  signal?: AbortSignal
}

export async function request<T>(config: RequestConfig): Promise<T> {
  const headers: Record<string, string> = { ...config.headers }

  // Attach the bearer token Arvel issued at login.
  const token = localStorage.getItem('access_token')
  if (token) headers['Authorization'] = `Bearer ${token}`

  const url = withQuery(config.url, config.params)
  const body = config.data !== undefined ? JSON.stringify(config.data) : undefined
  const res = await fetch(url, { method: config.method, headers, body, signal: config.signal })

  if (!res.ok) {
    // Arvel's error envelope: { "error": { "code", "message", "details" } }
    const errorBody = await res.json().catch(() => null)
    throw new ApiError(errorBody?.error?.message ?? `Request failed: ${res.status}`, res.status, errorBody)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}
```

> [!NOTE]
> `openapi-typescript`, `openapi-generator`, and the language-specific generators in the [Mobile clients](#mobile-clients) section all consume the same `openapi.yaml`. Orval isn't special — it's just what the kit happens to use.

<a name="keeping-the-client-in-sync"></a>
## Keeping the Client in Sync

Regenerate whenever the spec changes. The kit wraps both steps in one `make` target:

```makefile
api-generate:
	$(BACKEND) arvel openapi:export --output ../frontend/openapi.yaml --format yaml
	$(FRONTEND) npm run api:generate
```

```bash
make api-generate
```

Run this in CI on every backend change and fail if `git diff` shows uncommitted client output — that catches a contract change that nobody regenerated against. Pair it with `openapi:validate` so an invalid spec never gets that far.

<a name="authentication"></a>
## Authentication

Arvel's [built-in auth routes](../features/authentication.md#built-in-auth-routes) are designed to serve both browsers and native clients from the same endpoints. Register the [`AuthServiceProvider`](../features/authentication.md#registering-the-provider) to enable them.

`POST /api/auth/login` returns the access token in the **body** and sets the refresh and CSRF tokens as **cookies**:

```json
{
  "access_token": "eyJhbGci...",
  "token_type": "bearer",
  "expires_in": 900
}
```

```
Set-Cookie: __Host-refresh=...; HttpOnly; Secure; SameSite=Strict
Set-Cookie: _csrf=...; Secure; SameSite=Strict
```

Send the access token as a bearer header on every authenticated request:

```
Authorization: Bearer eyJhbGci...
```

`POST /api/auth/refresh` reads the `__Host-refresh` cookie and issues a fresh access token. `GET /api/auth/me` returns the current user wrapped in a `{ "data": { ... } }` envelope.

**Browser SPAs** get the refresh/CSRF cookies for free — the browser stores and resends them, so a silent refresh is just a `fetch('/api/auth/refresh')`. Keep the short-lived access token in memory (or `localStorage` if you accept the XSS trade-off, as the kit does) and let the HttpOnly refresh cookie do the long-term work.

See [Authentication](../features/authentication.md) for the full endpoint reference and the [Mobile clients](#mobile-clients) section for the bearer-only flow.

<a name="the-client-contract"></a>
## The Client Contract

Beyond individual endpoints, a few cross-cutting shapes hold across the whole API. Build your client's shared layer around them once.

### Error envelope

Every error — yours, a form request's, or FastAPI's body parsing — serializes identically:

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "The given data was invalid.",
    "details": [
      { "field": "email", "issue": "The email has already been taken." }
    ]
  }
}
```

`code` is a stable `UPPER_SNAKE_CASE` identifier, `message` is human-readable, and `details` appears only for field-level errors. Parse this once in your `request` mutator. The full code/status table lives in [Error Handling](../the-basics/error-handling.md#available-exceptions).

### Pagination

Paginated endpoints return `data`, `meta`, and `links`:

```json
{
  "data": [ /* items */ ],
  "meta": { "total": 142, "per_page": 20, "current_page": 2, "last_page": 8, "from": 21, "to": 40 },
  "links": { "first": 1, "prev": 1, "next": 3, "last": 8 }
}
```

For long, append-style mobile lists, prefer the [cursor paginator](../orm/query-builder.md#pagination) — it returns an opaque `next_cursor` instead of a page count and stays stable as rows shift.

### Rate limiting

Routes behind the [`Throttle`](../the-basics/middleware.md#throttle-rate-limiting) middleware return `429` with code `TOO_MANY_REQUESTS` and a `Retry-After` header once the limit is hit:

```python
from arvel.http.middleware import Throttle

router.middleware_group("api", [Throttle(60)])  # 60 requests/minute
```

Clients should honor `Retry-After` and back off rather than hammering the endpoint.

### Localization

Arvel negotiates locale from the `Accept-Language` header (see [Localization](../features/localization.md)). Set it on the client to get translated validation messages and content:

```
Accept-Language: ar
```

### Versioning

Version the API with a route-group [prefix](../the-basics/routing.md#prefixes) (`/api/v1`). Regenerate the client against each version's spec — never reach across versions in one client.

<a name="cors"></a>
## CORS for a Separate-Origin SPA

When the SPA is served from a different origin than the API (e.g. `app.example.com` calling `api.example.com`), the browser enforces CORS. Arvel ships a [`Cors` middleware](../the-basics/middleware.md#cors) (it extends Starlette's `CORSMiddleware`) but doesn't add it by default — register it on the ASGI app in your entrypoint:

```python
# public/asgi.py
from arvel.http.middleware import Cors

from bootstrap.app import create_application

asgi = create_application().into_asgi()

asgi.add_middleware(
    Cors,
    allowed_origins=["https://app.example.com"],  # never "*" with credentials
    allowed_methods=("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"),
    allowed_headers=("Authorization", "Content-Type", "X-CSRF-Token"),
    allow_credentials=True,                        # required for the refresh cookie
    max_age=600,
)
```

> [!WARNING]
> If your SPA relies on the refresh cookie, you **must** set `allow_credentials=True` and list explicit origins — `allow_credentials=True` with a wildcard origin raises `ValueError`. This is app-level wiring; it isn't part of the framework's baseline providers.

Serving the SPA and the API from the **same** origin (next section) sidesteps CORS entirely.

<a name="serving-a-spa"></a>
## Serving a Built SPA from Arvel

You can skip CORS by serving the built SPA from the same Arvel app. Build the frontend to static assets, then add a catch-all web route that returns the SPA shell for non-API paths so client-side routing works on refresh:

```python
# routes/web.py
from pathlib import Path

from arvel import Route
from starlette.requests import Request
from fastapi.responses import FileResponse

SPA_INDEX = Path("public/spa/index.html")


@Route.get("/{path:path}")
async def spa(request: Request, path: str) -> FileResponse:
    # API routes are registered first and take precedence; this only catches
    # everything else and hands it to the client-side router.
    return FileResponse(SPA_INDEX)
```

Mount the compiled assets as a [static directory](../the-basics/routing.md) and register API routes **before** this catch-all. The [e-commerce kit](../kits/ecommerce-kit.md) does exactly this in production.

<a name="realtime"></a>
## Realtime

Arvel's [broadcasting](../features/broadcasting.md) layer publishes named events on named channels through a pluggable driver — `redis-pubsub` for real delivery, `log`/`null` for development. A broadcast event carries a name (`broadcast_as()`) and a payload (`broadcast_with()`):

```python
class OrderShipped(Event, ShouldBroadcast):
    order_id: int

    def broadcast_on(self) -> Sequence[str]:
        return [f"orders.{self.order_id}"]

    def broadcast_as(self) -> str:
        return "order.shipped"

    def broadcast_with(self) -> Mapping[str, object]:
        return {"order_id": self.order_id}
```

Arvel ships a Pusher-protocol WebSocket server — **Reverb**. Start it with `arvel reverb:start` (install the `arvel[broadcasting]` extra first). With the `redis-pubsub` driver, the server subscribes to Redis and fans broadcasts out to connected clients, so multiple Reverb processes share one fan-out. Any Pusher client SDK connects without custom code:

```ts
// Web: pusher-js pointed at your Reverb server
import Pusher from 'pusher-js'

const pusher = new Pusher('<reverb-app-key>', {
  wsHost: import.meta.env.VITE_REVERB_HOST, // REVERB_HOST on the server
  wsPort: Number(import.meta.env.VITE_REVERB_PORT), // REVERB_PORT
  forceTLS: false,
  enabledTransports: ['ws', 'wss'],
})

pusher.subscribe('orders.1').bind('order.shipped', (data) => { /* update UI */ })
```

The same server works for mobile — `pusher-websocket-swift` (iOS), `pusher-websocket-java` (Android), and `dart_pusher_channels` (Flutter) all speak the same protocol.

Authorize who may listen on a channel with the [`Broadcast.channel`](../features/broadcasting.md#channels-and-authorization) decorator, and point the SDK's subscription-auth endpoint at it so private/presence channels are signed with the user's identity. The event name and payload your client binds to are exactly what `broadcast_as()` and `broadcast_with()` return.

<a name="push-notifications"></a>
## Push Notifications

Arvel's [notification](../features/notifications.md) system ships log, mail, database, and broadcast channels — there's **no built-in APNs/FCM channel**. To deliver native push, write a custom channel (any object with an `async send(notifiable, notification)` method) that calls your provider with the device tokens you collect from clients:

```python
class FcmChannel:
    async def send(self, notifiable: Any, notification: Notification) -> None:
        payload = notification.to_fcm(notifiable)  # your own method on the notification
        await fcm_client.send(tokens=notifiable.device_tokens, **payload)
```

Register it on the `NotificationManager` from a [service provider's](../core-concepts/service-providers.md) `boot()`, then list `"fcm"` in the notification's `via()` and add a matching `to_fcm()`:

```python
from arvel.notifications.manager import NotificationManager

class FcmServiceProvider(ServiceProvider):
    async def boot(self) -> None:
        self.container.make(NotificationManager).register_channel("fcm", FcmChannel())
```

The realtime path above (a WebSocket transport + a service worker / background socket) is the lower-effort alternative when you don't need OS-level push while the app is closed.

<a name="mobile-clients"></a>
## Mobile Clients

Native apps consume the same OpenAPI spec — generate a client in the platform's language:

| Platform | Generator |
|---|---|
| Swift | `openapi-generator` (`swift5`) or Apple's `swift-openapi-generator` |
| Kotlin / Android | `openapi-generator` (`kotlin`) |
| Flutter / Dart | `openapi-generator` (`dart-dio`) or `swagger_dart_code_generator` |

Three things differ from the browser:

- **Bearer-only auth.** Phones don't have a cookie jar tied to your domain, so treat the access token as primary. Store it in the platform secure store — **iOS Keychain** or **Android EncryptedSharedPreferences / Keystore**, never plain `UserDefaults` / `SharedPreferences`.
- **The refresh cookie won't ride along.** `__Host-refresh` is a browser cookie. A native HTTP client must capture the `Set-Cookie` from `/api/auth/login` and resend it to `/api/auth/refresh` itself, or you treat refresh as a re-login. Persist whatever you keep in the secure store, not in app memory or logs.
- **Locale comes from the device.** Send the device locale as `Accept-Language` so validation messages and content match the user's language (see [Localization](../features/localization.md)).

Everything else — the [error envelope](#the-client-contract), [pagination](#pagination), [rate limiting](#rate-limiting), and [realtime](#realtime) — is identical to the web client.
