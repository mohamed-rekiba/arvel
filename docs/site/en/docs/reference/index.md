# API Reference

This section is the map to Arvel’s public surface area. The pages below are **auto-generated from the source code** using [mkdocstrings](https://mkdocstrings.github.io/) (Google-style docstrings, members in source order). When you upgrade Arvel or pin a new minor release, regenerate the docs so signatures and narrative descriptions stay aligned with what actually ships.

Use these modules as entry points: they group the framework by concern—data layer, HTTP stack, bootstrap and providers, auth, caching, events, queues, validation, and the testing helpers. Subpackages expand into more specific types as you drill in.

## Core framework

**`arvel.data`** — ORM models, repositories, query builder, relationships, transactions, observers, and migrations-facing utilities. This is where typed **`Mapped`** columns and the repository pattern live.

**`arvel.http`** — Routing resources, controllers, requests, responses, and HTTP-facing glue that sits alongside FastAPI.

**`arvel.foundation`** — Application bootstrap, service container, providers, and lifecycle hooks that wire the framework together.

## Cross-cutting services

**`arvel.auth`** — Guards, user resolution, and authentication plumbing you integrate with your identity strategy.

**`arvel.cache`** — Cache contracts and drivers; swap implementations per environment without changing call sites.

**`arvel.events`** — Domain events, dispatch, and listener registration for decoupled reactions inside the app.

**`arvel.queue`** — Job types, dispatch, and queue contracts for async and background work.

**`arvel.validation`** — Validation rules and helpers that align with Arvel’s request and DTO patterns.

## Testing

**`arvel.testing`** — **`TestClient`**, **`TestResponse`**, **`DatabaseTestCase`**, **`ModelFactory`**, **`FactoryBuilder`**, and fakes for cache, mail, queue, storage, locks, media, notifications, events, and broadcasting.

---

::: arvel.data

::: arvel.http

::: arvel.foundation

::: arvel.auth

::: arvel.cache

::: arvel.events

::: arvel.queue

::: arvel.validation

::: arvel.testing
