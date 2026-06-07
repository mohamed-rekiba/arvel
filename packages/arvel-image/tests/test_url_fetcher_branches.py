"""Branch coverage for url_fetcher.py.

Pins the missing branches surfaced by the coverage report:
- 32-33: ``_safe_url``'s urlparse ValueError fallback
- 36-39: ``_safe_url``'s userinfo-stripping happy path
- 76-81: ``fetch_url``'s httpx ImportError branch
- 180:   ``sniff_image_mime``'s ``if fmt is None`` branch

Security focus: the userinfo-stripping tests are the credential-leak guard.
They MUST assert that the credential does not appear in the returned string,
not just that the URL is "different".
"""

from __future__ import annotations

import sys
from io import BytesIO
from typing import Any, Self

import pytest

pytest.importorskip("PIL", reason="arvel-image depends on Pillow for sniff_image_mime")

import arvel_image.media.url_fetcher as _uf
from arvel_image.media.url_fetcher import sniff_image_mime

# Module-internal helper — bypass pyright's reportPrivateUsage. Tests need to
# pin specific branches of `_safe_url` directly; going through the public API
# would couple the test to fetch_url's full network path.
_safe_url = getattr(_uf, "_safe_url")  # noqa: B009

# ─── _safe_url: urlparse ValueError fallback (L32-33) ────────────────────────


def test_safe_url_returns_placeholder_on_urlparse_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # L32-33: `except ValueError: return "<unparseable url>"`.
    # Patch urlparse to raise ValueError — that's the realistic failure mode
    # (malformed IPv6 literals like http://[::g]/ trigger it in some Python
    # versions, but the exact triggering input is version-dependent).
    import arvel_image.media.url_fetcher as uf

    def _raise_value_error(_url: str) -> Any:
        msg = "simulated urlparse failure"
        raise ValueError(msg)

    monkeypatch.setattr(uf, "urlparse", _raise_value_error)
    assert _safe_url("anything") == "<unparseable url>"


def test_safe_url_returns_placeholder_for_malformed_ipv6() -> None:
    # Real-world trigger for the ValueError branch — Python's urlparse can
    # raise on some malformed IPv6 literals. If this Python version doesn't
    # raise, the test still passes (the function returns the original URL),
    # because we have the monkeypatch test above as the explicit pin for the
    # except branch.
    result = _safe_url("http://[::g]/path")  # invalid IPv6
    # Either it raised (caught) → "<unparseable url>", or urlparse tolerated
    # it → original returned. Both are acceptable; the monkeypatch test pins
    # the actual exception path.
    assert result in ("<unparseable url>", "http://[::g]/path")


# ─── _safe_url: userinfo stripping (L36-39) — SECURITY PIN ───────────────────


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        # username only
        ("https://user@host.example.com/path", "https://host.example.com/path"),
        # username + password (the credential leak risk)
        ("https://user:secret@host.example.com/path", "https://host.example.com/path"),
        # password only (unusual but RFC-permitted)
        ("https://:secret@host.example.com/path", "https://host.example.com/path"),
        # userinfo + port
        ("https://user:pass@host.example.com:8443/path", "https://host.example.com:8443/path"),
        # userinfo at root path
        ("http://admin:hunter2@10.0.0.1/", "http://10.0.0.1/"),
    ],
    ids=["user_only", "user_pass", "pass_only", "with_port", "root_path"],
)
def test_safe_url_strips_userinfo(url: str, expected: str) -> None:
    result = _safe_url(url)
    assert result == expected


@pytest.mark.parametrize(
    ("url", "leaked_substrings"),
    [
        ("https://user:secret@host.example.com/path", ["secret", "user:", "user@"]),
        ("https://:hunter2@host.example.com/path", ["hunter2"]),
        ("http://admin:p%40ss@host/", ["p%40ss", "admin:", "admin@"]),
    ],
    ids=["password", "password_only", "url_encoded_password"],
)
def test_safe_url_credentials_not_present_in_output(url: str, leaked_substrings: list[str]) -> None:
    # The security guarantee — credentials must not appear anywhere in the
    # output, not just be "stripped" symbolically.
    result = _safe_url(url)
    for needle in leaked_substrings:
        assert needle not in result, (
            f"credential substring {needle!r} leaked into safe URL {result!r}"
        )


def test_safe_url_passthrough_for_clean_url() -> None:
    # Negative control — when there's no userinfo, the URL is returned as-is.
    clean = "https://api.example.com:8080/v1/users?limit=10"
    assert _safe_url(clean) == clean


# ─── fetch_url: httpx ImportError branch (L76-81) ────────────────────────────


@pytest.mark.asyncio
async def test_fetch_url_raises_helpful_import_error_when_httpx_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # L76-81: `try: import httpx except ImportError as exc: raise ImportError(<helpful msg>)`.
    # Force the import to fail by stashing None into sys.modules — Python's
    # import machinery raises ImportError when it encounters None there.
    from arvel_image.media.url_fetcher import fetch_url

    monkeypatch.setitem(sys.modules, "httpx", None)

    with pytest.raises(ImportError) as exc_info:
        await fetch_url("https://example.com/img.jpg", max_bytes=1024 * 1024)

    msg = str(exc_info.value)
    # The helpful message must name the install incantations.
    assert "httpx" in msg
    assert "pip install httpx" in msg
    assert "uv add httpx" in msg


# ─── sniff_image_mime: fmt is None branch (L180) ─────────────────────────────


def test_sniff_image_mime_returns_none_when_pillow_format_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # L179-180: `if fmt is None: return None`.
    # Pillow normally sets .format to the codec name ('JPEG', 'PNG', etc.).
    # On some edge cases (lazy decoders, custom plugins) it can be None even
    # though open() didn't raise. We test that branch by patching open() to
    # yield an image whose .format attribute is None.
    import arvel_image.media.url_fetcher as uf
    from PIL import Image as PILImage

    class _FormatNoneImage:
        format: str | None = None  # the branch trigger

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    def _fake_open(_fp: Any) -> _FormatNoneImage:
        return _FormatNoneImage()

    monkeypatch.setattr(PILImage, "open", _fake_open)

    # Input bytes don't matter — we're testing the post-open `fmt is None` branch.
    result = uf.sniff_image_mime(b"any bytes")
    assert result is None


def test_sniff_image_mime_returns_mime_for_real_jpeg() -> None:
    # Positive control — exercises the happy path (L181), confirming the
    # `fmt is None` branch is the only escape route besides the exception.
    from PIL import Image as PILImage

    buf = BytesIO()
    PILImage.new("RGB", (10, 10), (200, 100, 50)).save(buf, format="JPEG")
    result = sniff_image_mime(buf.getvalue())
    assert result == "image/jpeg"


def test_sniff_image_mime_returns_none_for_garbage_bytes() -> None:
    # Positive control for the existing exception branch (L174-178).
    result = sniff_image_mime(b"not an image at all")
    assert result is None
