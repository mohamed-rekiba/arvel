"""The queue deserializer resolves job classes from a registry, never by importing the name
the payload carries (GH-301).

`deserialize` calls what it resolves — `job_cls(*args, **kwargs)` — so importing a
payload-supplied `module:qualname` would hand anyone with broker write access arbitrary code
execution on every worker. These tests pin the guard: registered jobs still round-trip, and
anything unregistered is refused *without* its module being imported.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from typing import Any

import pytest

from arvel.queue import Job, deserialize, deserialize_any, deserialize_instance, serialize
from arvel.queue.serialization import _JOB_REGISTRY, _qualified_name, serialize_instance


class RegisteredJob(Job):
    def __init__(self, value: str = "") -> None:
        self.value = value

    async def handle(self) -> str:
        return self.value


async def test_subclassing_registers_the_job() -> None:
    assert _JOB_REGISTRY[_qualified_name(RegisteredJob)] is RegisteredJob


async def test_registered_job_round_trips_through_args_payload() -> None:
    job = await deserialize(serialize(RegisteredJob, ("hello",), {}))
    assert isinstance(job, RegisteredJob)
    assert job.value == "hello"


async def test_registered_job_round_trips_through_instance_payload() -> None:
    job = await deserialize_instance(serialize_instance(RegisteredJob("state")))
    assert isinstance(job, RegisteredJob)
    assert job.value == "state"


@pytest.mark.parametrize("target", ["os:system", "subprocess:run", "builtins:eval"])
async def test_unregistered_target_is_refused(target: str) -> None:
    """The RCE shape: a tampered payload naming an arbitrary callable must not be invoked."""
    payload = f'{{"job": "{target}", "args": ["echo pwned"], "kwargs": {{}}}}'
    with pytest.raises(ValueError, match="unregistered job class"):
        await deserialize(payload)


async def test_unregistered_target_is_refused_on_the_instance_rail() -> None:
    payload = '{"job": "os:system", "state": {}}'
    with pytest.raises(ValueError, match="unregistered job class"):
        await deserialize_any(payload)


async def test_refusal_happens_without_importing_the_named_module() -> None:
    """The membership test must *replace* the import, not follow it.

    Importing an attacker-named module runs its module-level side effects before any
    post-hoc `issubclass` check could fire — so a guard that imports first and validates
    after is not a guard at all.

    The probe module must be genuinely **importable** but not yet imported: naming a
    module that doesn't exist would make the `sys.modules` assertion pass against an
    import-first implementation too, which would pin nothing.
    """
    victim = "xml.dom.pulldom"  # real, stdlib, and nothing in arvel imports it
    assert importlib.util.find_spec(victim) is not None, (
        "probe must be importable, or this test passes vacuously"
    )
    # Evicting it is what keeps the assertion honest if an earlier test imported it — but put
    # whatever was there back, or we'd leave later tests running against a different sys.modules
    # than they'd otherwise see (order-dependent failures).
    previous = sys.modules.pop(victim, None)
    try:
        with pytest.raises(ValueError, match="unregistered job class"):
            await deserialize(f'{{"job": "{victim}:parse", "args": [], "kwargs": {{}}}}')

        assert victim not in sys.modules, "the deserializer imported a payload-supplied module"
    finally:
        if previous is not None:
            sys.modules[victim] = previous


@pytest.mark.parametrize(
    "framework_job",
    [
        "arvel.mail:SendQueuedMailable",
        "arvel.notifications:SendQueuedNotification",
        "arvel.queue.listener:CallQueuedListener",
        "arvel.queue.broadcast:CallQueuedBroadcast",
    ],
)
def test_framework_jobs_resolve_in_a_cold_worker(framework_job: str) -> None:
    """The framework's own queued jobs must load in a process that imported nothing else.

    This runs in a **subprocess** on purpose. All four live in modules kept lazy for the G2
    startup contract, so they only register if something imported them — and every in-process
    test does exactly that, which makes the registry look populated when a real worker's would
    be empty. Asserting in-process would pass while queued mail broke on deploy.
    """
    probe = (
        "import arvel.queue as q\n"
        "from arvel.queue.serialization import _JOB_REGISTRY, _load_job\n"
        "assert not _JOB_REGISTRY, f'expected a cold registry, got {sorted(_JOB_REGISTRY)}'\n"
        f"cls = _load_job({framework_job!r})\n"
        f"assert cls.__name__ == {framework_job.split(':')[1]!r}\n"
        "print('ok')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, f"cold-boot resolution failed:\n{result.stderr}"
    assert "ok" in result.stdout


def test_cold_worker_still_refuses_an_arbitrary_name() -> None:
    """The framework-job carve-out must not become a general import escape."""
    probe = (
        "import arvel.queue as q\n"
        "from arvel.queue.serialization import _load_job\n"
        "try:\n"
        "    _load_job('os:system')\n"
        "except ValueError:\n"
        "    print('refused')\n"
        "else:\n"
        "    raise SystemExit('os:system was resolved')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stderr
    assert "refused" in result.stdout


async def test_registered_job_cannot_smuggle_an_arbitrary_listener_ref() -> None:
    """`CallQueuedListener` passes the job allowlist legitimately — its *state* must not reopen it.

    `deserialize_instance` setattrs every key in the payload's `state`, so a tampered message can
    name a registered job class and still control `listener_ref`. That used to reach
    `_load(listener_ref)` and then `handle(*args)` with attacker-supplied arguments — the original
    defect's shape, through an approved class.
    """
    from arvel.queue.listener import CallQueuedListener

    payload = (
        '{"job": "arvel.queue.listener:CallQueuedListener", "state": '
        '{"listener_ref": "os:system", "is_class": true, "listener_state": null, '
        '"args": ["echo pwned"]}}'
    )
    job = await deserialize_any(payload)
    assert isinstance(job, CallQueuedListener)  # the job class itself is legitimately loadable

    with pytest.raises(ValueError, match="unregistered listener"):
        await job.handle()


async def test_registered_queued_listener_still_resolves() -> None:
    """The listener guard must not break the legitimate path."""
    from arvel.events.dispatcher import ShouldQueue
    from arvel.queue.listener import CallQueuedListener

    class Greeter(ShouldQueue):
        seen: list[str] = []

        def handle(self, value: str) -> str:
            Greeter.seen.append(value)
            return value

    job = CallQueuedListener.for_listener(Greeter, ("hi",))
    assert await job.handle() == "hi"
    assert Greeter.seen == ["hi"]


async def test_registry_is_keyed_by_qualified_name_not_bare_class_name() -> None:
    """Two same-named jobs in different modules must not collide."""

    class Shadow(Job):
        async def handle(self) -> Any:
            return None

    key = _qualified_name(Shadow)
    assert ":" in key
    assert _JOB_REGISTRY[key] is Shadow
