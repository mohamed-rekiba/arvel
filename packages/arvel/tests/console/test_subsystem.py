"""Tests for ``arvel.console._subsystem``."""

from __future__ import annotations

import pytest
from arvel.console._subsystem import (
    FOUNDATION_SUBSYSTEMS,
    CliSubsystem,
    closure,
)


class TestCliSubsystemEnum:
    def test_contains_required_members(self) -> None:
        required = {
            "CONFIG",
            "LOG",
            "LANG",
            "CONTEXT",
            "OBSERVABILITY",
            "DATABASE",
            "HTTP",
            "SCHEDULER",
            "QUEUE",
            "CACHE",
            "MAIL",
            "STORAGE",
            "BROADCAST",
            "AUTH",
            "EVENTS",
            "USER_PROVIDERS",
        }
        assert required.issubset({m.name for m in CliSubsystem})

    def test_is_str_enum(self) -> None:
        assert isinstance(CliSubsystem.HTTP.value, str)
        assert CliSubsystem.HTTP.value == "http"


class TestFoundationSubsystems:
    def test_exactly_foundation_members(self) -> None:
        assert (
            frozenset(
                {
                    CliSubsystem.CONFIG,
                    CliSubsystem.LOG,
                    CliSubsystem.LANG,
                    CliSubsystem.CONTEXT,
                }
            )
            == FOUNDATION_SUBSYSTEMS
        )


class TestClosure:
    def test_empty_returns_empty(self) -> None:
        assert closure(frozenset()) == frozenset()

    def test_no_implicit_foundation(self) -> None:
        """``closure`` is a pure graph walk — foundation is injected by the bootstrap."""
        result = closure(frozenset({CliSubsystem.HTTP}))
        assert CliSubsystem.CONFIG not in result
        assert CliSubsystem.LOG not in result

    def test_queue_pulls_database(self) -> None:
        result = closure(frozenset({CliSubsystem.QUEUE}))
        assert result == frozenset({CliSubsystem.QUEUE, CliSubsystem.DATABASE})

    def test_auth_pulls_database(self) -> None:
        result = closure(frozenset({CliSubsystem.AUTH}))
        assert result == frozenset({CliSubsystem.AUTH, CliSubsystem.DATABASE})

    def test_multiple_inputs_merge(self) -> None:
        result = closure(frozenset({CliSubsystem.QUEUE, CliSubsystem.AUTH, CliSubsystem.HTTP}))
        assert result == frozenset(
            {
                CliSubsystem.QUEUE,
                CliSubsystem.AUTH,
                CliSubsystem.HTTP,
                CliSubsystem.DATABASE,
            }
        )

    def test_leaf_node_returns_itself(self) -> None:
        result = closure(frozenset({CliSubsystem.STORAGE}))
        assert result == frozenset({CliSubsystem.STORAGE})

    def test_user_providers_is_leaf(self) -> None:
        result = closure(frozenset({CliSubsystem.USER_PROVIDERS}))
        assert result == frozenset({CliSubsystem.USER_PROVIDERS})


class TestCycleValidation:
    def test_import_succeeds(self) -> None:
        """No real cycle exists. Module already imported above — assert that's fine."""
        import arvel.console._subsystem as mod

        assert mod.closure is closure

    def test_cycle_detection_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Inject a cycle and re-run the validator to confirm it raises."""
        import arvel.console._subsystem as mod

        bad_edges = {
            CliSubsystem.QUEUE: frozenset({CliSubsystem.CACHE}),
            CliSubsystem.CACHE: frozenset({CliSubsystem.QUEUE}),
        }
        monkeypatch.setattr(mod, "_DEPENDENCY_EDGES", bad_edges)
        with pytest.raises(RuntimeError, match="cycle"):
            mod.validate_no_cycles()
