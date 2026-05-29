"""NFR-013-012 — Optional pusher-js contract test (requires Node + npm)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def _node_available() -> bool:
    return shutil.which("node") is not None and shutil.which("npm") is not None


_SKIP_REASON = "Node.js/npm not installed; contract test skipped."


@pytest.mark.skipif(not _node_available(), reason=_SKIP_REASON)
def test_pusher_js_client_connects_and_subscribes() -> None:
    """NFR-013-012 AC1: real pusher-js client subscribes and receives events."""
    contract_dir = Path(__file__).parent / "contract"
    if not (contract_dir / "package.json").exists():
        pytest.skip("Contract harness not scaffolded yet (added in WI-013-S3).")

    npm = shutil.which("npm")
    assert npm is not None
    result = subprocess.run(  # noqa: S603 — npm path resolved via shutil.which
        [npm, "test"],
        cwd=contract_dir,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, f"pusher-js contract failed:\n{result.stdout}\n{result.stderr}"
