"""Validate intra-repo Markdown links in the contributor docs tree.

The public site under `docs/site` is already checked by `mkdocs build --strict`.
Nothing checks the engineering docs that mkdocs never sees — `docs/README.md`
and the guides it links into (architecture, subsystems, ORM, HTTP, console,
contributing, packages, reference, kits). This script flags links to files that
don't exist and `#anchors` that don't resolve, so the contributor hub doesn't
rot silently.

The ADR archive under `docs/adr` is deliberately out of scope: ADRs are an
append-only decision log, not navigable documentation.

Run: `uv run python scripts/check_doc_links.py` (exit 1 on any broken link).
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_ROOT = REPO_ROOT / "docs"

# The reader-facing engineering docs — the tree docs/README.md links into.
CHECKED_DIRS = (
    "architecture",
    "console",
    "contributing",
    "http",
    "kits",
    "orm",
    "packages",
    "reference",
    "subsystems",
)
CHECKED_ROOT_FILES = ("README.md", "threat-model.md")

EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "tel:", "ftp://", "//")

_INLINE_LINK = re.compile(r"!?\[[^\]]*\]\(\s*(<[^>]+>|[^)\s]+)")
_HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*$")
_EXPLICIT_ANCHOR = re.compile(r'<a\s+(?:name|id)\s*=\s*"([^"]+)"')
_ATTR_ID = re.compile(r"\{#([A-Za-z0-9_-]+)\}")
_INLINE_CODE = re.compile(r"`[^`]*`")
_FENCE = re.compile(r"^\s*(?:```|~~~)")


def iter_docs() -> Iterator[Path]:
    """Yield every Markdown file in the checked contributor-docs tree."""
    for name in CHECKED_ROOT_FILES:
        candidate = DOCS_ROOT / name
        if candidate.is_file():
            yield candidate
    for sub in CHECKED_DIRS:
        yield from sorted((DOCS_ROOT / sub).rglob("*.md"))


def slugify(heading: str) -> str:
    """Turn heading text into a GitHub-style anchor slug.

    Matches github-slugger: each whitespace char maps to one hyphen with no
    collapsing, so a removed punctuation char (e.g. an arrow between words)
    leaves a double hyphen — exactly what GitHub renders.
    """
    text = re.sub(r"[^\w\s-]", "", heading.strip().lower())
    return re.sub(r"\s", "-", text)


def parse(text: str) -> tuple[set[str], list[tuple[int, str]]]:
    """Extract (anchors, links) from Markdown, ignoring fenced code blocks."""
    anchors: set[str] = set()
    links: list[tuple[int, str]] = []
    in_fence = False
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _FENCE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        heading = _HEADING.match(raw)
        if heading is not None:
            anchors.add(slugify(heading.group(1)))
        anchors.update(_EXPLICIT_ANCHOR.findall(raw))
        anchors.update(_ATTR_ID.findall(raw))
        cleaned = _INLINE_CODE.sub("", raw)
        links.extend((lineno, m.group(1).strip("<>")) for m in _INLINE_LINK.finditer(cleaned))
    return anchors, links


def resolve(target: str, source: Path) -> tuple[Path, str | None] | None:
    """Map a link target to (path, anchor); None for links we don't check."""
    if target.startswith(EXTERNAL_PREFIXES):
        return None
    path_part, _, fragment = target.partition("#")
    anchor = fragment or None
    if path_part == "":
        return source, anchor
    if path_part.startswith("/"):
        base = REPO_ROOT / path_part.lstrip("/")
    else:
        base = source.parent / path_part
    return base.resolve(), anchor


def anchors_of(path: Path, cache: dict[Path, set[str]]) -> set[str]:
    """Return (and memoize) the anchors a Markdown file defines."""
    key = path.resolve()
    if key not in cache:
        cache[key] = parse(path.read_text(encoding="utf-8"))[0] if path.is_file() else set()
    return cache[key]


def check_link(
    target: str,
    source: Path,
    cache: dict[Path, set[str]],
) -> str | None:
    """Return an error message for a broken link, or None when it resolves."""
    resolved = resolve(target, source)
    if resolved is None:
        return None
    path, anchor = resolved
    if not path.exists():
        return f"missing target -> {target}"
    if anchor is None or path.suffix.lower() != ".md":
        return None
    if anchor not in anchors_of(path, cache):
        return f"missing anchor '#{anchor}' in {target}"
    return None


def main() -> int:
    """Check every contributor doc and report broken links."""
    cache: dict[Path, set[str]] = {}
    errors: list[str] = []
    file_count = 0
    for doc in iter_docs():
        file_count += 1
        _, links = parse(doc.read_text(encoding="utf-8"))
        rel = doc.relative_to(REPO_ROOT)
        for lineno, target in links:
            message = check_link(target, doc, cache)
            if message is not None:
                errors.append(f"{rel}:{lineno}: {message}")
    if errors:
        print(f"Found {len(errors)} broken link(s) across {file_count} files:")
        for error in errors:
            print(f"  {error}")
        return 1
    print(f"Checked links in {file_count} files; all resolve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
