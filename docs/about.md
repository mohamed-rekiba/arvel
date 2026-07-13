# About arvel

**arvel** is a batteries-included, async-first web framework for Python. It gives you an
expressive application layer — routing, an ORM, a queue, a cache, mail, validation, auth,
and more — on a modern, fully type-safe foundation, without making you assemble a dozen
libraries yourself.

## Philosophy

- **Async-first.** Every I/O path is `async`; blocking work is pushed to worker threads so
  the event loop stays responsive.
- **Type-safe, end to end.** The whole package passes `mypy --strict` and `pyright --strict`
  with no blanket suppressions. Your editor knows what everything is.
- **Light to import.** `import arvel` pulls in zero heavy third-party libraries — each engine
  is loaded lazily, the first time you actually use it.
- **A modular monolith.** One deployable, cleanly separated modules, enforced import
  boundaries — the benefits of separation without the distributed-systems tax.
- **Convention over configuration.** Sensible defaults, escape hatches when you need them.

## Inspiration & prior art

arvel's developer experience is inspired by a mature PHP framework whose elegant, productive
application layer set the bar for what a full-stack framework can feel like. arvel is an
independent project — it shares none of that framework's code — but it owes its ergonomic
sensibility to that design lineage, and we gratefully acknowledge it here.

## Built on great open source

arvel is an application layer over a curated set of best-in-class libraries. We stand on the
shoulders of these projects:

| Capability | Engine |
|------------|--------|
| HTTP / ASGI | [Litestar](https://litestar.dev) |
| ORM & SQL | [SQLAlchemy](https://www.sqlalchemy.org) Core + [Alembic](https://alembic.sqlalchemy.org) |
| Validation & serialization | [msgspec](https://jcristharif.com/msgspec/) |
| Dates & times | [whenever](https://github.com/ariebovenberg/whenever) |
| Console | [Typer](https://typer.tiangolo.com) |
| Cache | [cashews](https://github.com/Krukov/cashews) |
| Storage | [fsspec](https://filesystem-spec.readthedocs.io) |
| Mail | [aiosmtplib](https://aiosmtplib.readthedocs.io) |
| Notifications | [Apprise](https://github.com/caronc/apprise) |
| Templates | [Jinja2](https://jinja.palletsprojects.com) |
| Queue & scheduling | [taskiq](https://taskiq-python.github.io) |
| Full-text search | [Meilisearch](https://www.meilisearch.com) |
| Password hashing | [pwdlib](https://github.com/frankie567/pwdlib) (Argon2) |
| Images / video | [Pillow](https://python-pillow.org) / [PyAV](https://github.com/PyAV-Org/PyAV) |
| Localization (CLDR) | [Babel](https://babel.pocoo.org) |

Thank you to every maintainer and contributor of these libraries.

## License

arvel is open source under the **[MIT License](https://opensource.org/licenses/MIT)**.

```
Copyright (c) arvel contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction …
```

See the [`LICENSE`](https://github.com/mohamed-rekiba/arvel/blob/main/LICENSE) file in the
repository for the full text.

## See also

- [Get started](getting-started.md) — install arvel and build your first route.
- [Architecture](architecture.md) — how the modular monolith and import boundaries fit together.
