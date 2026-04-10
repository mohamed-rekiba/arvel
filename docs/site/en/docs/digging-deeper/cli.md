# Arvel CLI

If you have spent any time with Laravel, you already know the rhythm: one entry point, many subcommands, and generators that keep your hands on the keyboard instead of copy-pasting boilerplate. Arvel brings that same feeling to async Python. The `arvel` command is built on **Typer**, so help text, options, and nested groups feel natural in the terminal.

At **v0.1.0** (Python 3.14+), the CLI is the spine of day-to-day work—migrations, queues, the scheduler, routes, health probes, and more—without leaving your shell.

## What ships out of the box

Running `arvel` with no subcommand prints the banner and help. Core groups include:

- **`db`** — database workflows (migrations, seeders, and related tasks)
- **`make`** — code generators (models, repositories, policies, and friends)
- **`view`** — materialized view helpers where your app uses them
- **`queue`** — worker and queue management
- **`schedule`** — run or daemonize the scheduler that dispatches due jobs
- **`route`** — introspect and cache routes
- **`health`** — probe configured subsystems from the command line
- **`serve`** — run the development server
- **`about`**, **`config`**, **`tinker`**, **`publish`** — ergonomics and introspection
- **`new`** — scaffold a new project
- **`up` / `down`** — maintenance mode toggles

That list mirrors how Arvel thinks about an application: data, background work, time-based work, HTTP surface, and observability—all reachable under one name.

## Custom commands

Arvel scans `app/Console/Commands/` for Python files that export a `typer.Typer` instance. Each file becomes its own command group, named after the file stem. Drop a new Typer app in that folder, restart nothing permanent, and your team gets a first-class command next to the framework’s.

```python
import typer

my_app = typer.Typer(help="Domain-specific maintenance tasks.")


@my_app.command("sync-catalog")
def sync_catalog() -> None:
    """Example custom command."""
    typer.echo("Sync started…")


# Export `my_app` from app/Console/Commands/catalog.py → group name: catalog
```

## Typical workflows

**Run pending migrations and seed data** (exact flags depend on your project’s `db` commands—`arvel db --help` is the source of truth).

**Dispatch the scheduler once** (useful in cron or a systemd timer):

```python
# Often paired with app/schedule.py registering jobs on a Scheduler instance.
# CLI: arvel schedule run
```

**Start a queue worker** so `Job` subclasses actually execute outside the request cycle:

```python
# CLI: arvel queue work  (see --help for your driver’s options)
```

**Check connectivity** before a deploy:

```python
# arvel health check
# Probes database, cache, and queue using your configured settings.
```

## Why it feels like Laravel

One binary, predictable verbs, generators that match framework conventions, and room for your own Typer apps without a plugin ceremony. Arvel’s CLI is not a thin wrapper—it is the operational front door for the same concepts you configure in code: `QueueContract`, `Scheduler`, routes, and health.

When in doubt, `arvel <group> --help` stays honest about what your installed version can do.
