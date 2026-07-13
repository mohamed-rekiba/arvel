"""arvel describes capabilities generically — no reference-framework or ecosystem brand names
anywhere in the tree. The token list is assembled from fragments so this guard passes its own
scan; the check is the same one a reviewer would run by hand."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# fragments, not literals, so this file is not itself a hit. Plain substring matching (no
# word boundaries): a token buried in an identifier (a CamelCase class, a snake_case config
# key) is exactly the regression this guard exists to catch.
_TOKENS = [
    "lara" + "vel",
    "elo" + "quent",
    "arti" + "san",
    "bla" + "de",
    "sym" + "fony",
    "illu" + "minate",
    "sanc" + "tum",
    "pen" + "nant",
]
_BANNED = re.compile("|".join(_TOKENS), re.IGNORECASE)

_SCAN_SUFFIXES = {".py", ".md", ".sh", ".pyi", ".html", ".toml", ".yaml", ".yml", ".tmpl"}

#: root-level files that ship or render publicly — the package metadata is the most visible
#: surface of all
_ROOT_FILES = ("README.md", "pyproject.toml", "zensical.toml", "mkdocs.yml")


def test_tree_is_brand_free() -> None:
    hits: list[str] = []
    scan: list[Path] = [
        path
        for tree in ("src", "tests", "tools", "docs")
        for path in (ROOT / tree).rglob("*")
        if path.suffix in _SCAN_SUFFIXES and path.name != Path(__file__).name
    ]
    scan.extend(ROOT / name for name in _ROOT_FILES if (ROOT / name).exists())
    for path in scan:
        for lineno, line in enumerate(path.read_text(errors="ignore").splitlines(), 1):
            if _BANNED.search(line):
                hits.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()[:90]}")
    assert not hits, "brand tokens found:\n" + "\n".join(hits)
