"""Process — async subprocess runner over `asyncio.create_subprocess_exec` (`Process`
parity, never shell=True): run/start/pool, `ProcessResult` predicates, `throw()`, and timeout
kill."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from arvel.support import Process, ProcessFailed, ProcessTimedOut


async def test_run_a_successful_command() -> None:
    result = await Process.run([sys.executable, "-c", "print('hi')"])
    assert result.successful() is True
    assert result.failed() is False
    assert result.output().strip() == "hi"
    assert result.exit_code == 0


async def test_run_a_failing_command() -> None:
    result = await Process.run([sys.executable, "-c", "import sys; sys.exit(3)"])
    assert result.successful() is False
    assert result.failed() is True
    assert result.exit_code == 3


async def test_stderr_is_captured_separately() -> None:
    result = await Process.run(
        [sys.executable, "-c", "import sys; sys.stderr.write('oops'); sys.exit(1)"]
    )
    assert result.error_output().strip() == "oops"
    assert result.output() == ""


async def test_throw_raises_process_failed_on_non_zero_exit() -> None:
    result = await Process.run([sys.executable, "-c", "import sys; sys.exit(1)"])
    with pytest.raises(ProcessFailed) as excinfo:
        result.throw()
    assert excinfo.value.result is result


async def test_throw_is_a_no_op_and_returns_self_on_success() -> None:
    result = await Process.run([sys.executable, "-c", "print('ok')"])
    assert result.throw() is result


async def test_input_is_piped_to_stdin() -> None:
    result = await Process.run(
        [sys.executable, "-c", "import sys; print(sys.stdin.read().strip().upper())"],
        input="hello",
    )
    assert result.output().strip() == "HELLO"


async def test_start_returns_a_handle_that_wait_resolves() -> None:
    handle = await Process.start([sys.executable, "-c", "print('async')"])
    result = await handle.wait()
    assert result.successful() is True
    assert result.output().strip() == "async"


async def test_pool_runs_concurrently_and_preserves_order() -> None:
    commands = [
        [sys.executable, "-c", "print(1)"],
        [sys.executable, "-c", "print(2)"],
        [sys.executable, "-c", "print(3)"],
    ]
    results = await Process.pool(commands)
    assert [r.output().strip() for r in results] == ["1", "2", "3"]
    assert all(r.successful() for r in results)


async def test_timeout_kills_the_process_and_raises() -> None:
    with pytest.raises(ProcessTimedOut):
        await Process.run(
            [sys.executable, "-c", "import time; time.sleep(5)"],
            timeout=0.05,
        )


async def test_timeout_none_lets_a_quick_command_finish_normally() -> None:
    result = await Process.run([sys.executable, "-c", "print('fast')"], timeout=5)
    assert result.output().strip() == "fast"


async def test_env_is_passed_through() -> None:
    result = await Process.run(
        [sys.executable, "-c", "import os; print(os.environ.get('ARVEL_TEST_VAR'))"],
        env={"ARVEL_TEST_VAR": "42"},
    )
    assert result.output().strip() == "42"


async def test_cwd_changes_the_working_directory(tmp_path: Path) -> None:
    result = await Process.run(
        [sys.executable, "-c", "import os; print(os.getcwd())"],
        cwd=str(tmp_path),
    )
    assert result.output().strip() == str(tmp_path)


async def test_never_shells_out_arguments_are_literal() -> None:
    """A shell-metacharacter argument must be treated literally, not interpreted (no shell=True)."""
    result = await Process.run([sys.executable, "-c", "import sys; print(sys.argv[1])", "$(rm)"])
    assert result.output().strip() == "$(rm)"
