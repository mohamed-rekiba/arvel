"""quality gate #34 — CLI exit-code honesty.

: no command in the surface produces a "success" exit code (0)
without doing real work. Bucket-A real-wire-up commands (migrate, cache:*) exit 0
only after their backing call returns success; bucket-C honest-deferral commands
(key:rotate) exit 2 with a tracking-issue pointer.

This test enforces the gate at the unit-test level by verifying that the once-
stubbed commands no longer print "<thing> succeeded" while their underlying
implementation returns nothing useful.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest


class TestCacheClearHonesty:
    """+ : cache:clear fails when subsystem unbound."""

    def test_clear_does_not_print_success_on_failure(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from arvel.console.commands.cache_commands import clear

        with (
            patch("arvel.facades.cache.Cache.store", side_effect=RuntimeError("not bound")),
            pytest.raises(RuntimeError),
        ):
            asyncio.run(clear(None))

        captured = capsys.readouterr()
        assert "Cache cleared" not in captured.out, (
            "cache:clear must not print 'Cache cleared.' when the underlying flush failed; "
            "the bare-except swallow from before WI-021 is back."
        )


class TestCacheForgetHonesty:
    """+ : cache:forget fails when subsystem unbound."""

    def test_forget_does_not_print_success_on_failure(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from arvel.console.commands.cache_commands import forget

        with (
            patch("arvel.facades.cache.Cache.store", side_effect=RuntimeError("not bound")),
            pytest.raises(RuntimeError),
        ):
            asyncio.run(forget("k", None))

        captured = capsys.readouterr()
        assert "Removed" not in captured.out


class TestKeyRotateHonesty:
    """+ : key:rotate exits 2 with NotImplementedError messaging."""

    def test_key_rotate_does_not_exit_zero_for_unimplemented_path(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from arvel.console import Context
        from arvel.console.commands.key_rotate import KeyRotateCommand

        code = KeyRotateCommand().handle(Context())
        captured = capsys.readouterr()
        assert code != 0
        assert "rows updated" not in captured.out.lower()
        assert "rotated" not in captured.out.lower()
