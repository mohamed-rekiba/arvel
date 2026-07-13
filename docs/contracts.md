# Contracts

arvel's **contracts** are a set of `Protocol` interfaces that define the core services the framework
provides — the container, the application, config, logging, translation, event dispatch. They live in
`arvel.contracts` and are **semver-stable**: the concrete implementations can change between releases,
but the contracts they satisfy do not.

## Introduction

Because they are `typing.Protocol`s, contracts are **structural** — a class satisfies a contract by
having the right methods, with no explicit subclassing or registration. That makes them ideal for two
things: type-annotating what you depend on, and swapping an implementation without touching callers.

```python
from arvel.contracts import ConfigRepository

def configure(config: ConfigRepository) -> None:
    dsn = config.get("database.default")   # depends on the contract, not a concrete class
```

## When to use contracts

Reach for a contract when you want a **loose coupling point** — a service you might reimplement, a
seam you want to mock in a test, or a library you're publishing that shouldn't bind callers to arvel's
concrete classes. For ordinary application code, depending on the concrete helper (`config(...)`,
`app(...)`) is simpler and perfectly fine; contracts earn their keep at boundaries.

## How to use contracts

Resolve the concrete implementation from the container, annotated by its contract:

```python
from arvel.contracts import Logger

class ReportService:
    def __init__(self, log: Logger) -> None:   # autowired to the bound concrete logger
        self._log = log

    def run(self) -> None:
        self._log.bind(job="report").info("started")
```

The container resolves the constructor's annotated dependencies, so binding your own implementation of
a contract makes every consumer use it — no consumer changes required. See
[Service Container](container.md).

## Contract reference

| Contract | Defines |
|----------|---------|
| `Container` | Bind abstractions to concretes and resolve them |
| `Application` | The container that registers providers and boots them |
| `ServiceProvider` | `register` (bindings) + `boot` (wiring) lifecycle |
| `ConfigRepository` | Dotted-key configuration access (`config('app.name')`) |
| `Logger` | Structured logger — `bind` context, `channel` selection |
| `Translator` | Localization lookup with placeholders + pluralization |
| `ExceptionHandler` | The single global handler (HTTP + console + queue) |
| `EventDispatcher` | Event dispatch the ORM/queue resolve against |
| `CommandOutput` | The console output surface shared by commands and seeders |

## See also

- [Service Container](container.md) — how contracts are bound and resolved.
- [Service Providers](providers.md) — where you bind your own implementations.
- [Facades](facades.md) — the static-accessor counterpart to resolving a contract.
