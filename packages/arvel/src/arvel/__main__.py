"""Enable ``python -m arvel`` — the fallback target for the venv re-exec shim."""

from __future__ import annotations

from arvel.console.entrypoint import main

if __name__ == "__main__":
    main()
