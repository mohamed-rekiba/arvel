"""arvel.views.vite — the Vite manifest reader.

Python owns the server + the Inertia protocol but NOT the JS build (doc 09): the separate
``frontend/`` toolchain produces ``public/build/manifest.json``, and arvel only *reads* it to
emit hashed ``<script>``/``<link>`` tags. No Node, no bundling here. Exposed to templates as
the ``vite()`` global.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast


class Vite:
    """Reads a Vite manifest and emits asset tags / resolves hashed URLs for entries."""

    def __init__(
        self, manifest_path: str = "public/build/manifest.json", base: str = "/build"
    ) -> None:
        self.manifest_path = manifest_path
        self.base = base.rstrip("/")
        self._manifest: dict[str, Any] | None = None

    def _load(self) -> dict[str, Any]:
        loaded = self._manifest
        if loaded is None:
            loaded = cast("dict[str, Any]", json.loads(Path(self.manifest_path).read_text()))
            self._manifest = loaded
        return loaded

    def _chunk(self, entry: str) -> dict[str, Any]:
        manifest = self._load()
        if entry not in manifest:
            raise KeyError(f"Vite manifest has no entry for {entry!r}")
        return cast("dict[str, Any]", manifest[entry])

    def asset(self, entry: str) -> str:
        """The hashed public URL for an entry's built file."""
        return f"{self.base}/{self._chunk(entry)['file']}"

    def tags(self, *entries: str) -> str:
        """``<link>`` (css) + module ``<script>`` tags for the given entries."""
        lines: list[str] = []
        for entry in entries:
            chunk = self._chunk(entry)
            for css in chunk.get("css", []):
                lines.append(f'<link rel="stylesheet" href="{self.base}/{css}">')
            lines.append(f'<script type="module" src="{self.base}/{chunk["file"]}"></script>')
        return "\n".join(lines)


def vite(*entries: str) -> str:
    """Template helper: emit asset tags for ``entries`` from the default manifest location."""
    return Vite().tags(*entries)
