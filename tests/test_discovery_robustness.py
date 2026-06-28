"""Phase E / It.7 — discovery robustness: one broken ecosystem package's entry point must not crash
provider discovery (and with it the whole app boot). The failure is isolated + warned."""

from __future__ import annotations

from typing import Any

import pytest
from structlog.testing import capture_logs

from arvel.kernel import discovery


class _GoodProvider: ...


class _FakeEntryPoint:
    def __init__(self, name: str, loader: Any) -> None:
        self.name = name
        self._loader = loader

    def load(self) -> Any:
        return self._loader()


def test_a_failing_entry_point_is_skipped_not_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> Any:
        raise ImportError("broken ecosystem package")

    eps = [
        _FakeEntryPoint("good", lambda: _GoodProvider),
        _FakeEntryPoint("bad", boom),
    ]
    monkeypatch.setattr(discovery.md, "entry_points", lambda group=None: eps)

    with capture_logs() as logs:
        result = discovery._load_entry_points([])

    assert result == [_GoodProvider]  # the good provider loads; the broken one is skipped
    assert any(log.get("event") == "provider_entry_point_load_failed" for log in logs)


def test_dont_discover_still_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    eps = [
        _FakeEntryPoint("good", lambda: _GoodProvider),
        _FakeEntryPoint("skipme", lambda: object),
    ]
    monkeypatch.setattr(discovery.md, "entry_points", lambda group=None: eps)
    assert discovery._load_entry_points(["skipme"]) == [_GoodProvider]
