# AI: Workflows

Some AI work outlives a single request — a multi-step agent run, a
human-in-the-loop approval, retries across hours. arvel's fire-and-forget
[queue](../queues.md) isn't the right shape for that: you need **durable
execution** that survives restarts and can suspend waiting for a signal.
`arvel-ai` gives you one stable workflow API with a swappable engine.

```python
from arvel_ai.workflows import workflow, Workflow

@workflow(name="onboard")
async def onboard(ctx, user_id: int) -> str:
    approved = await ctx.wait_signal("approved")   # durably suspends (real engine)
    return "welcome" if approved else "rejected"

handle = await Workflow.start("onboard", 42)
await Workflow.signal(handle.id, "approved", True)
status = await Workflow.status(handle.id)           # running | completed | failed
```

The contract is engine-neutral — arvel-owned `WorkflowHandle` / `WorkflowStatus`,
never an engine type — so swapping engines is a config change, not a rewrite.

## Drivers

Set `ai.workflows.default`:

| Driver | Use when | Needs |
|---|---|---|
| `queue` (default) | short multi-step jobs; no new infrastructure | just arvel |
| `temporal` | long-lived, retry-across-hours, human-in-the-loop | `uv add 'arvel-ai[temporal]'` + a Temporal server |
| `fake` | tests (`Workflow.fake()`) | — |

**The `queue` default has an honest ceiling:** it runs the workflow on
`arvel.queue` and tracks state in a store, but signals are **cooperative** —
`ctx.wait_signal` reads what's already been delivered; it does not durably
suspend a paused execution the way a real engine does. It's right for short,
mostly-linear jobs and it reserves the contract so upgrading to Temporal is a
config edit.

## Temporal (real durable execution)

```python
# config/ai.py
ai = {
    "workflows": {
        "default": "temporal",
        "drivers": {"temporal": {
            "target": "temporal.internal:7233",
            "namespace": "default",
            "task_queue": "myapp",
        }},
    },
}
```

`arvel-ai` is the **client** side (start / signal / status). Running the
workflows needs a Temporal **worker** process that registers the same behaviour
against Temporal — that's app deployment (see the Temporal Python SDK's worker
docs). The integration test in the package (`test_workflow_temporal.py`) shows a
full start → signal → durable-suspend → complete against a real Temporal server
(`docker-compose.test.yml`).

## Common mistakes & gotchas

- **`temporal` driver needs the extra** — `uv add 'arvel-ai[temporal]'`; a
  missing engine tells you exactly that.
- **The queue driver's signals are cooperative** — don't build a long
  human-in-the-loop pause on it; use Temporal for that.
- **Register the workflow before starting it** — `@workflow(name=...)` must have
  run (import the module) or `start` raises `KeyError`.

## See also

- [AI](ai.md) · [MCP Server](ai-mcp.md) — the rest of the AI package.
- [Queues](../queues.md) — for fire-and-forget background jobs.
