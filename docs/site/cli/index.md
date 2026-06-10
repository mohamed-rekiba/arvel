# CLI

The `arvel` command is your day-to-day interface — scaffold code, run migrations, work queues, export OpenAPI, and inspect what's registered.

## Start here

**[Command Reference](commands.md)** — every command, grouped by namespace, with options and exit codes.

## Daily commands

| Task | Command |
|---|---|
| Dev server | `arvel serve --reload` |
| Migrations | `arvel migrate` / `arvel migrate:status` |
| Seed data | `arvel db:seed` |
| Queue worker | `arvel queue:work` |
| Scheduler tick | `arvel schedule:run` |
| List routes | `arvel route:list` |
| Export API spec | `arvel openapi:export -o docs/api/openapi.yaml` |
| REPL | `arvel shell` |
| Scaffolding | `arvel make:model Post -mf` |

## Custom commands

Generate a stub with `arvel make:command`, declare `requires` for framework DI, and use `schedule_async` for database work — see [Writing custom commands](commands.md#custom-commands).

## See also

- [Needs-based bootstrap](commands.md#needs-based-bootstrap) — why `make:*` is instant but `migrate` boots the database.
- [Service Providers](../core-concepts/service-providers.md#contributing-cli-commands) — register commands from a provider.
