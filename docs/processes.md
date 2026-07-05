# Processes

`Process` runs external commands over `asyncio.create_subprocess_exec`
— **never a shell**. Every argument is passed through to the OS literally, so there's no
shell-injection surface: a value like `"$(rm -rf /)"` is just a string argument, never
interpreted.

```python
from arvel.support import Process

result = await Process.run(["echo", "hi"])
result.successful()        # True
result.output().strip()    # "hi"
result.exit_code           # 0
```

## `ProcessResult`

A frozen dataclass with the command, exit code, and captured output:

```python
result.command       # ["echo", "hi"]
result.exit_code     # 0
result.stdout         # "hi\n"
result.stderr         # ""

result.successful()   # exit_code == 0
result.failed()       # not successful()
result.output()       # stdout
result.error_output() # stderr
```

`throw()` raises `ProcessFailed` when the command failed, and returns `self` (chainable) when it
succeeded — handy at the end of a call you don't want to silently ignore a failure from:

```python
from arvel.support import ProcessFailed

try:
    (await Process.run(["false"])).throw()
except ProcessFailed as exc:
    print(exc.result.exit_code, exc.result.error_output())
```

## Options

```python
await Process.run(
    ["python", "-c", "print('hi')"],
    timeout=5.0,                       # seconds; None (default) means no timeout
    cwd="/srv/app",                    # working directory
    env={"MY_VAR": "1"},               # merged... actually replaces the child's env entirely
    input="some stdin data",           # piped to the command's stdin
)
```

## Timeouts

A `timeout` that's exceeded **kills the process (and its process group, so any children it spawned
die too)** and raises `ProcessTimedOut` — it never leaves an orphaned or zombie process behind:

```python
from arvel.support import ProcessTimedOut

try:
    await Process.run(["sleep", "30"], timeout=1.0)
except ProcessTimedOut as exc:
    print(f"{exc.command} timed out after {exc.timeout}s")
```

## Long-running processes — `start`/`wait`

`run()` awaits the whole command to completion. When you need to do other work while a command is
executing (or hold a handle to it), use `start()`:

```python
handle = await Process.start(["python", "long_task.py"])
# ... do other things ...
result = await handle.wait()   # blocks until it exits, then returns a ProcessResult
```

## Running several commands concurrently — `pool`

`pool()` runs a batch of commands **concurrently** and returns their results **in the same order
as the input** — regardless of which one finishes first:

```python
results = await Process.pool([
    ["curl", "-s", "https://a.example/health"],
    ["curl", "-s", "https://b.example/health"],
    ["curl", "-s", "https://c.example/health"],
])
[r.successful() for r in results]   # matches the input order
```

## Common mistakes & gotchas

- **Passing a single string instead of an argv list.** `Process.run("ls -la")` is wrong — there's
  no shell to split it. Always pass a list: `["ls", "-la"]`.
- **Assuming `env=` merges with the parent environment.** It replaces it entirely (the same as
  Python's `subprocess`); pass `{**os.environ, "MY_VAR": "1"}` if you want to extend rather than
  replace.
- **Forgetting `throw()` returns `self`, not `None`, on success** — you can chain `.output()` right
  after it: `(await Process.run([...])).throw().output()`.

## How it works

`Process` execs argv directly via `asyncio.subprocess`, in a new process group
(`start_new_session=True`), so a timeout can `killpg` the whole tree rather than leaving orphaned
children behind. `pool()` is a thin `asyncio.gather` over `run()` — Python's ordinary
"gather preserves input order" guarantee is what gives you ordered results from concurrent work.

## See also

- [Concurrency](concurrency.md) — offloading CPU-bound *Python* work (as opposed to external
  commands) off the event loop.
