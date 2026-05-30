---
hide:
  - navigation
  - toc
title: Arvel — the clean stack for Python developers and agents
description: A typed, async-first Python web framework with Laravel-grade developer experience, built on FastAPI + Pydantic + SQLAlchemy.
---

<div class="arvel-hero" markdown>

<h1 class="arvel-hero__title">
The clean stack for
<span class="arvel-hero__accent">Python developers and agents</span>.
</h1>

<p class="arvel-hero__lede">
A Python web framework that feels good to write and impossible to misuse &mdash; expressive routing, a typed ORM, and first-class async from the request loop to the database.
</p>

<div class="arvel-hero__actions" markdown>
[Get started](installation.md){ .md-button .md-button--primary }
[View on GitHub](https://github.com/mohamed-rekiba/arvel){ .md-button }
</div>

</div>

<div class="arvel-pillars" markdown>

<div class="arvel-pillar" markdown>
:material-rocket-launch-outline:{ .arvel-pillar__icon }

### Easy

One command to scaffold. One import to wire a route, send a mail, or dispatch a job. Arvel ships with `Route`, `Cache`, `Mail`, `Bus`, and `DB` already wired together &mdash; so you write the feature, not the plumbing.

</div>

<div class="arvel-pillar" markdown>
:material-shield-check-outline:{ .arvel-pillar__icon }

### Typed

Your editor knows the shape of every model, every route parameter, every config value. Mistakes show up as red squiggles &mdash; not as 500 errors at midnight. Pass a wrong argument anywhere and the IDE tells you before you even save the file.

</div>

<div class="arvel-pillar" markdown>
:material-lightning-bolt-outline:{ .arvel-pillar__icon }

### Fast

Concurrent by default &mdash; handle thousands of requests without threads or callbacks. Database queries, cache reads, queue dispatch, and mail sends all run without blocking. Your app stays responsive even under load.

</div>

</div>

## The `arvel` CLI

One command line for the work you do every day: start an app, generate files, run migrations, inspect routes, and keep workers moving.

=== "First app"

    ```bash
    # Create it
    uv tool install arvel
    arvel new my-app

    # Run it
    cd my-app
    arvel serve

    # Check it
    arvel route:list
    arvel openapi:export
    ```

    Start a real app, run it locally, then check what Arvel registered for you. No Uvicorn flags to memorize before you see your first route.

=== "Scaffolding"

    ```bash
    # Generate typed stubs — no boilerplate to hand-write
    arvel make:model Post
    arvel make:migration CreatePostsTable
    arvel make:controller PostController --resource --model=Post
    arvel make:factory PostFactory
    arvel make:policy PostPolicy
    arvel make:job PublishPost
    arvel make:mail PostPublished
    arvel make:request StorePostRequest
    ```

    Every generator normalises the name — `post`, `Post`, and `post_model` all produce `class Post`. Generated files pass `ruff` and `mypy --strict` immediately.

=== "Database"

    ```bash
    arvel migrate               # run pending migrations
    arvel migrate:status        # see which migrations have run
    arvel migrate:rollback      # undo the last batch
    arvel migrate:fresh         # drop everything and re-run from scratch

    arvel db:seed               # run your seeders
    arvel db:show               # list tables, row counts, and sizes
    arvel db:table posts        # inspect a table's columns and indexes
    ```

=== "Inspect"

    ```bash
    arvel route:list                       # every registered route
    arvel route:list --filter posts        # filter by path substring
    arvel route:list --json | jq '.'       # machine-readable output

    arvel event:list                       # all listeners per event class
    arvel schedule:list                    # scheduled tasks and their cron
    arvel channel:list                     # WebSocket channels (Reverb)

    arvel about                            # framework + runtime versions
    arvel openapi:export                   # dump OpenAPI spec to YAML/JSON
    ```

=== "Queue"

    ```bash
    # Workers
    arvel queue:work                       # process jobs continuously
    arvel queue:work --stop-when-empty     # drain once and exit (CI/cron)
    arvel queue:work --queue high,default  # multiple queues, in priority order

    # Failed job management
    arvel queue:failed                     # list failed jobs with details
    arvel queue:retry all                  # requeue every failed job
    arvel queue:retry 5                    # requeue a single job by ID
    arvel queue:forget 5                   # delete one failed job
    arvel queue:flush                      # delete all failed jobs
    arvel queue:prune-failed --hours=48    # prune failures older than N hours
    arvel queue:clear                      # clear all pending jobs from a queue
    arvel queue:restart                    # signal workers to reload gracefully
    ```

    Generate a new job class with `arvel make:job PublishPost`.

=== "Scheduler"

    ```bash
    # Run the scheduler
    arvel schedule:work                    # daemon — ticks every minute forever
    arvel schedule:run                     # run due tasks once, then exit (cron mode)

    # Inspect the schedule
    arvel schedule:list                    # show all tasks, cron expression, next run
    ```

    Run `schedule:work` as a long-lived process alongside your queue worker. Use `schedule:run` when you already have an external cron (`* * * * *`) and just want Arvel to handle the task dispatch.

    Generate a scheduled command with `arvel make:command DailyReport` then register it in your `App\Console\Kernel`.

For Docker, CI setup, and source builds see [Installation](installation.md). For the full command reference see [Console](console.md).

## Why Arvel?

Arvel brings Laravel's everyday developer experience to async Python.

The key ideas are:

- **Laravel-like**: Routes, controllers, facades, providers, queues, scheduler, resources, and a CLI that feels familiar.
- **Python-native**: Built on FastAPI, Starlette, Pydantic, SQLAlchemy, and Uvicorn, so it stays close to the tools Python teams already use.
- **Typed**: Editor feedback, strict models, typed config, and fewer runtime surprises.
- **Async-first**: Requests, database work, queues, cache, mail, and storage are designed for async apps.
- **App-ready**: PostgreSQL, MySQL, SQLite, MongoDB, Redis, AMQP, S3, and local storage are part of the normal path.
- **Less glue code**: Generate the boring files and spend your time on the feature.
