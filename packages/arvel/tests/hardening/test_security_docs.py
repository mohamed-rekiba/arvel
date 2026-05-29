"""WI-017 / FR-017-016, FR-017-017, FR-017-020."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SECURITY_DIR = REPO_ROOT / "docs" / "security"
THREAT_MODEL = REPO_ROOT / "docs" / "threat-model.md"
VERSIONING_POLICY = REPO_ROOT / "docs" / "strategy" / "versioning-policy.md"


def test_security_review_docs_exist() -> None:
    """FR-017-016: per-area security review reports exist."""
    assert SECURITY_DIR.exists(), "docs/security/ must exist"
    expected = {"http-auth", "broadcasting", "query-builder", "cache", "storage"}
    found = {p.stem.replace("review-", "") for p in SECURITY_DIR.glob("review-*.md")}
    missing = expected - found
    assert not missing, (
        f"FR-017-016: missing per-area review docs for: {sorted(missing)}; got {sorted(found)}"
    )


def test_threat_model_exists_with_stride_table() -> None:
    """FR-017-017: threat model with STRIDE coverage."""
    assert THREAT_MODEL.exists(), "FR-017-017: docs/threat-model.md must exist"
    text = THREAT_MODEL.read_text(encoding="utf-8")
    for category in (
        "Spoofing",
        "Tampering",
        "Repudiation",
        "Information",
        "Denial",
        "Elevation",
    ):
        assert category in text, f"threat model must reference STRIDE category {category!r}"


def test_versioning_policy_exists() -> None:
    """FR-017-020: SemVer policy committed."""
    assert VERSIONING_POLICY.exists(), "FR-017-020: docs/strategy/versioning-policy.md must exist"
    text = VERSIONING_POLICY.read_text(encoding="utf-8")
    for marker in ("MAJOR", "MINOR", "PATCH", "Deprecation"):
        assert marker in text, f"versioning policy must cover {marker!r}"
