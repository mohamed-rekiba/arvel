# Workflows (durable execution)

Some work outlives a single request — an order that moves through authorize → fulfil → ship over
hours, a job that must survive a restart halfway through, a multi-step process you need to watch and
resume. arvel's [queue](../queues.md) is fire-and-forget; it isn't built to *remember* where a
long-running process got to. **`arvel-workflow`** is: a standalone, opt-in package that gives you
**durable execution** — backed by [Temporal](https://temporal.io) — with arvel's ergonomics instead
of Temporal's setup tax.

> **Separate package, not core.** `arvel-workflow` is installed on its own and pulls the engine
> behind an extra — a web process that never runs a workflow pays nothing for it.
>
> ```bash
> uv add 'arvel-workflow[temporal]'
> ```
>
> **Scope note (early release).** Today the package ships the durable-execution core: define
> workflows and activities, run a worker, start work and read its result. The richer surface —
> signals, queries, human-in-the-loop updates, child workflows, sagas — is on the [roadmap](#roadmap)
> below and **not shipped yet**. This page documents only what runs today.

## The one idea: workflow vs activity

Two roles, and the split is the whole model:

- A **workflow** is the *orchestration* — the steps and their order. Its body must be
  **deterministic**, so it does **no I/O directly**.
- An **activity** is a *single step that does I/O* — a DB write, an API call, sending mail. Activities
  run outside the determinism sandbox, so they're free to do real work.

That constraint is a gift in arvel: **the activity is exactly where the container plugs in.** Your
activities call arvel facades (`Cache`, `DB`, `Mail`, `AI`, …) like any other code; your workflow
bodies stay pure. You never write Temporal's `imports_passed_through` boilerplate — the framework
handles the sandbox for you.

## Define an activity, then a workflow

Both autoload by convention — drop a file in the folder and it's registered, no wiring.

```python
# app/activities/greet.py
from arvel_workflow import activity
from arvel import Cache

@activity
async def greet(name: str) -> str:
    count = await Cache.increment("greet:count")   # activities do I/O — arvel DI works here
    return f"hello {name} (#{count})"
```

```python
# app/workflows/greet.py
from arvel_workflow import workflow, run_activity
from app.activities.greet import greet          # a plain import — no ceremony

@workflow
class Greet:
    async def run(self, name: str) -> str:
        return await run_activity(greet, name)     # the body stays pure; the activity does the work
```

## Run the worker

The worker is the process that executes workflows. One command autoloads `app/workflows/` +
`app/activities/` and starts polling:

```bash
arvel workflow:work            # connect to your configured Temporal server
arvel workflow:work --dev      # or boot an ephemeral local server — nothing to install first
```

`--dev` is the "first-run with zero infrastructure" path: it starts a throwaway local Temporal
server (downloading the dev-server binary once), so you can see a workflow run before standing up any
services.

## Start it and read the result

The `Workflow` facade is the client side — connect once, start work, await the outcome:

```python
handle = await app.make("workflow").start(Greet, "world")
result = await app.make("workflow").result(handle)   # "hello world (#1)"
```

`start` returns a durable handle you can hold and come back to; `result` awaits completion.

## Configure

One typed file; the defaults are sensible for local dev:

```python
# config/workflow.py
config = {
    "target": "localhost:7233",   # your Temporal server
    "namespace": "default",
    "task_queue": "arvel",
}
```

## Test it

Exercise workflows against Temporal's local test server rather than mocks — a mock can't reproduce
the sandbox, so it wouldn't prove your workflow actually runs. Boot the app, run the worker
in-process, drive it through the facade, and assert on the real result (and any side effects your
activities left, e.g. via a faked `Cache`). See the package's testing guide for the full pattern.

## Roadmap

Not shipped yet — coming as the package grows:

- **Signals / queries / updates** — send an event into a running workflow, read its live state, and
  drive human-in-the-loop approvals.
- **Child workflows & fan-out** — one workflow orchestrating many.
- **Sagas & compensation**, **durable timers/sleep**, **scheduled workflows**, and per-activity
  **retry/timeout** sugar.
- A **time-skipping test harness** so a multi-day wait runs in milliseconds.

## See also

- **The package docs** — the full guide (getting started, defining workflows + activities, running
  the worker, configuration, testing): the [`arvel-workflow`](https://pypi.org/project/arvel-workflow/)
  README and its `docs/`.
- [Queues & Jobs](../queues.md) — for fire-and-forget background work (a different tool).
- [AI](ai.md) — the AI gateway, if your activities call models.
