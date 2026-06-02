# arvel-ecommerce-kit

A full-stack reference application, not a library. It proves the core framework plus `arvel-permission` and `arvel-image` on a real domain: a multi-vendor e-commerce store with catalog, cart, checkout, RBAC, and media.

**Source**: `kits/arvel-ecommerce-kit/` — `backend/` (Arvel app) and `frontend/` (Vue 3 + Vite SPA).

## What's in it

```
kits/arvel-ecommerce-kit/
├── backend/
│   ├── bootstrap/        # app.py, providers.py
│   ├── app/              # models, http/controllers, observers, providers
│   ├── config/           # auth, cache, permission.py, image, …
│   ├── database/         # migrations (incl. RBAC + media), seeders
│   └── routes/           # web.py, api.py
├── frontend/             # Vue 3 + Vite, Orval-generated API client
├── docker-compose.yml    # PostgreSQL + Redis
└── Makefile
```

The backend is a normal Arvel app — it has its own `bootstrap/app.py` calling `create_application()`. Use it as a worked example of how the pieces in this documentation fit together in a non-trivial codebase.

## Providers it wires

`backend/bootstrap/providers.py` registers `CacheServiceProvider`, `SchedulerServiceProvider`, `EventServiceProvider`, `QueueServiceProvider`, `BroadcastServiceProvider`, `StorageServiceProvider`, `ImageServiceProvider`, `MailServiceProvider`, `AuthServiceProvider`, and the app's own `AppServiceProvider`.

> **Note**: The kit uses `arvel-permission`'s **models and traits** on its `User` (with an inlined RBAC migration) but does **not** register `PermissionServiceProvider`. So the Gate `before` hook and `apply_*_config` from the package don't run — RBAC checks go through the kit's own wiring. It also doesn't register `OAuthServiceProvider`, `SearchServiceProvider`, or `AuditServiceProvider`.

## Workspace status

The kit is picked up by the `kits/*` workspace glob, but unlike the five libraries it's **not** listed in the root `[tool.uv.sources]` or the dev dependency group. CI type-checks and tests target the five libraries; the kit is exercised through its own tests and `Makefile`.

## See also

- [Bootstrap & lifecycle](../architecture/bootstrap-lifecycle.md) — what `create_application()` does.
- [arvel-permission](../packages/permission.md) · [arvel-image](../packages/image.md)
