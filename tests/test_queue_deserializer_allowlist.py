"""The queue deserializer resolves job classes from a registry, never by importing the name
the payload carries (GH-301).

`deserialize` calls what it resolves — `job_cls(*args, **kwargs)` — so importing a
payload-supplied `module:qualname` would hand anyone with broker write access arbitrary code
execution on every worker. These tests pin the guard: registered jobs still round-trip, and
anything unregistered is refused *without* its module being imported.
"""

from __future__ import annotations

import importlib.util
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
    sys.modules.pop(victim, None)

    with pytest.raises(ValueError, match="unregistered job class"):
        await deserialize(f'{{"job": "{victim}:parse", "args": [], "kwargs": {{}}}}')

    assert victim not in sys.modules, "the deserializer imported a payload-supplied module"


async def test_registry_is_keyed_by_qualified_name_not_bare_class_name() -> None:
    """Two same-named jobs in different modules must not collide."""

    class Shadow(Job):
        async def handle(self) -> Any:
            return None

    key = _qualified_name(Shadow)
    assert ":" in key
    assert _JOB_REGISTRY[key] is Shadow
