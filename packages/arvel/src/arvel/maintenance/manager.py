"""On-disk maintenance-mode marker."""

from __future__ import annotations

import json
import secrets as _secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class MaintenanceMarker:
    """Snapshot of the maintenance marker file."""

    secret: str
    retry: int | None
    refresh: int | None
    template: str | None
    started_at: datetime


_DEFAULT_PATH = Path("storage/framework/down")


class MaintenanceModeManager:
    """Reads and writes the maintenance marker file.

    The marker lives at ``storage/framework/down`` by default and contains
    JSON: ``{"secret", "retry", "refresh", "template", "started_at"}``.
    """

    def __init__(self, marker_path: Path | None = None) -> None:
        self._marker_path: Path = marker_path or _DEFAULT_PATH

    @property
    def marker_path(self) -> Path:
        return self._marker_path

    def is_down(self) -> bool:
        return self._marker_path.exists()

    def read_marker(self) -> MaintenanceMarker | None:
        if not self._marker_path.exists():
            return None
        try:
            raw = json.loads(self._marker_path.read_text())
        except OSError, json.JSONDecodeError:
            return None
        started = raw.get("started_at")
        started_at = (
            datetime.fromisoformat(started) if isinstance(started, str) else datetime.now(UTC)
        )
        return MaintenanceMarker(
            secret=str(raw.get("secret", "")),
            retry=raw.get("retry"),
            refresh=raw.get("refresh"),
            template=raw.get("template"),
            started_at=started_at,
        )

    def down(
        self,
        *,
        secret: str | None = None,
        retry: int | None = None,
        refresh: int | None = None,
        template: str | None = None,
    ) -> MaintenanceMarker:
        if secret is None:
            secret = _secrets.token_urlsafe(32)
        marker = MaintenanceMarker(
            secret=secret,
            retry=retry,
            refresh=refresh,
            template=template,
            started_at=datetime.now(UTC),
        )
        self._marker_path.parent.mkdir(parents=True, exist_ok=True)
        self._marker_path.write_text(
            json.dumps(
                {
                    "secret": marker.secret,
                    "retry": marker.retry,
                    "refresh": marker.refresh,
                    "template": marker.template,
                    "started_at": marker.started_at.isoformat(),
                },
                indent=2,
            )
        )
        return marker

    def up(self) -> None:
        """Remove the marker. Idempotent — no error if absent."""
        try:
            self._marker_path.unlink()
        except FileNotFoundError:
            return
