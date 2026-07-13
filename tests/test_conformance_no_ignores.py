"""The model-host contract (DR-0037) erased the mixin ignore clusters — keep them erased.

A new `type: ignore` in these modules means a typing hole is being patched
instead of fixed; the count is pinned at the current floor."""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).parent.parent / "src" / "arvel"

#: module → maximum allowed `type: ignore` occurrences (0 unless a documented,
#: reviewed exception exists — see the module for its reason)
CEILINGS = {
    "search/__init__.py": 0,
    "activitylog/__init__.py": 0,
    # one documented exception: the lazy taskiq broker decorator (untyped third-party seam)
    "queue/__init__.py": 1,
}


def test_mixin_modules_stay_ignore_free() -> None:
    for rel, ceiling in CEILINGS.items():
        count = (SRC / rel).read_text().count("type: ignore")
        assert count <= ceiling, (
            f"{rel}: {count} ignores (ceiling {ceiling}) — fix the type, not the checker"
        )
