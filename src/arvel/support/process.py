"""arvel.support.process — an async subprocess runner (Laravel `Process` parity).

Always execs argv directly via `asyncio.create_subprocess_exec` — never a shell — so there is no
shell-injection surface; every argument is passed through literally. A `timeout` kills the whole
process group (children survive a single-process kill) and raises `ProcessTimedOut`.

    result: ProcessResult = await Process.run(["echo", "hi"])
    handle: InvokedProcess = await Process.start([...]); result = await handle.wait()
    results = await Process.pool([cmd1, cmd2])          # concurrent, ordered
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


class ProcessFailed(RuntimeError):
    """Raised by `ProcessResult.throw()` when the command exited non-zero (Laravel `throw()`)."""

    def __init__(self, result: ProcessResult) -> None:
        super().__init__(
            f"process {list(result.command)!r} exited {result.exit_code}: {result.stderr.strip()}"
        )
        self.result = result


class ProcessTimedOut(RuntimeError):
    """Raised when a command exceeds its `timeout` — the process (group) is killed first."""

    def __init__(self, command: Sequence[str], timeout: float | None) -> None:
        super().__init__(f"process {list(command)!r} timed out after {timeout}s")
        self.command = command
        self.timeout = timeout


@dataclass(frozen=True, slots=True)
class ProcessResult:
    """The outcome of a completed `Process.run`/`pool` invocation."""

    command: Sequence[str]
    exit_code: int
    stdout: str
    stderr: str

    def successful(self) -> bool:
        return self.exit_code == 0

    def failed(self) -> bool:
        return not self.successful()

    def output(self) -> str:
        return self.stdout

    def error_output(self) -> str:
        return self.stderr

    def throw(self) -> ProcessResult:
        """Raise `ProcessFailed` on a non-zero exit; otherwise return self (chainable)."""
        if self.failed():
            raise ProcessFailed(self)
        return self


def _exit_code(process: asyncio.subprocess.Process) -> int:
    """`returncode` is only `None` before the process exits; `communicate()` always waits for
    exit, so this is unreachable in practice — narrows the type without an `assert` in library code."""
    code = process.returncode
    if code is None:
        raise RuntimeError("process has no exit code after communicate()")
    return code


def _kill(process: asyncio.subprocess.Process) -> None:
    """Kill the whole process group when possible — a plain `process.kill()` leaves any children
    the command spawned running."""
    with contextlib.suppress(ProcessLookupError, PermissionError, AttributeError):
        os.killpg(process.pid, signal.SIGKILL)
        return
    with contextlib.suppress(ProcessLookupError):
        process.kill()


async def _start(
    command: Sequence[str],
    *,
    cwd: str | None,
    env: Mapping[str, str] | None,
    needs_stdin: bool,
) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        env=dict(env) if env is not None else None,
        stdin=asyncio.subprocess.PIPE if needs_stdin else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,  # its own process group, so a timeout can kill children too
    )


class InvokedProcess:
    """A running process started via `Process.start` — `await .wait()` for its `ProcessResult`."""

    def __init__(
        self, command: Sequence[str], process: asyncio.subprocess.Process, input: str | None
    ) -> None:
        self._command = command
        self._process = process
        self._input = input

    @property
    def pid(self) -> int:
        return self._process.pid

    async def wait(self) -> ProcessResult:
        stdin_bytes = self._input.encode() if self._input is not None else None
        stdout, stderr = await self._process.communicate(stdin_bytes)
        return ProcessResult(
            command=self._command,
            exit_code=_exit_code(self._process),
            stdout=stdout.decode(),
            stderr=stderr.decode(),
        )


class Process:
    """Static namespace for running subprocesses (Laravel `Process` parity)."""

    @staticmethod
    async def start(
        command: Sequence[str],
        *,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
        input: str | None = None,
    ) -> InvokedProcess:
        process = await _start(command, cwd=cwd, env=env, needs_stdin=input is not None)
        return InvokedProcess(command, process, input)

    @staticmethod
    async def run(
        command: Sequence[str],
        *,
        timeout: float | None = None,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
        input: str | None = None,
    ) -> ProcessResult:
        process = await _start(command, cwd=cwd, env=env, needs_stdin=input is not None)
        stdin_bytes = input.encode() if input is not None else None
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(stdin_bytes), timeout)
        except TimeoutError:
            _kill(process)
            await process.wait()
            raise ProcessTimedOut(command, timeout) from None
        return ProcessResult(
            command=command,
            exit_code=_exit_code(process),
            stdout=stdout.decode(),
            stderr=stderr.decode(),
        )

    @staticmethod
    async def pool(
        commands: Sequence[Sequence[str]],
        *,
        timeout: float | None = None,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> list[ProcessResult]:
        """Run every command concurrently, returning results in the same order as `commands`."""
        return list(
            await asyncio.gather(
                *(Process.run(cmd, timeout=timeout, cwd=cwd, env=env) for cmd in commands)
            )
        )
