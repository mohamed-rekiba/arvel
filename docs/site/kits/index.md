# Kits

Starter kits are full project templates — backend, frontend, and infra wired together. Scaffold with `arvel new --kit <name>`.

## Available kits

| Kit | Command | Doc |
|---|---|---|
| API (default) | `arvel new my-app` | [Getting started](../getting-started/installation.md) |
| E-commerce | `arvel new my-shop --kit ecommerce` | [E-commerce kit](ecommerce-kit.md) |

The e-commerce kit includes Postgres, Valkey, MinIO, a Vue storefront + admin, RBAC, media uploads, and an Orval-generated API client — use it as a reference implementation or a starting point.

```bash
arvel new my-shop --kit ecommerce
cd my-shop
make env && make up && make migrate && make seed
# → http://localhost:8002
```

## See also

- [Frontend integration](../frontend/integration.md) — how the kit keeps the OpenAPI client in sync.
- [Companion packages](../packages/README.md) — permission, image, and audit wired in the kit.
