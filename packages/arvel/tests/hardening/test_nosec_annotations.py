"""Every # nosec carries a rule code and a rationale."""

from __future__ import annotations

import re
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[3] / "arvel" / "src" / "arvel"
# Any line containing '# nosec' (with or without bracketed codes)
NOSEC_RE = re.compile(r"#\s*nosec(?:\s|\[)")
# Accepted inline forms (both must include a CWE code AND a rationale after a colon):
#   # nosec B110: rationale here          (bandit-canonical space form)
#   # nosec[B110]: rationale here         (bracket form)
#   # nosec B110,B311: rationale here     (multiple codes, space form)
#   # nosec[B110,B311]: rationale here    (multiple codes, bracket form)
NOSEC_OK = re.compile(r"#\s*nosec(?:\s+|\[)(?P<codes>B\d{3}(?:,B\d{3})*)\]?\s*[:\-]\s*\S+")
NOSEC_CODE_ONLY = re.compile(r"#\s*nosec\s+B\d{3}(?:,B\d{3})*\s*$")


def _scan_python_files() -> list[Path]:
    return list(SRC_ROOT.rglob("*.py"))


def test_no_bare_nosec_comments() -> None:
    """every '# nosec' must carry a rule code and a rationale."""
    offenders: list[tuple[Path, int, str]] = []
    for path in _scan_python_files():
        lines = path.read_text(encoding="utf-8").splitlines()
        for n, line in enumerate(lines, 1):
            if not NOSEC_RE.search(line):
                continue
            if NOSEC_OK.search(line):
                continue
            previous = lines[n - 2].strip() if n > 1 else ""
            if NOSEC_CODE_ONLY.search(line) and previous.startswith("# "):
                continue
            offenders.append((path.relative_to(SRC_ROOT.parent.parent), n, line.strip()))
    assert not offenders, (
        "every '# nosec' must be '# nosec B###: <rationale>' "
        "(or '# nosec[B###]: <rationale>'). Offenders:\n"
        + "\n".join(f"  {p}:{n} -> {ln}" for p, n, ln in offenders)
    )
