"""Exhaustive coverage for ``HasMedia.coerce_source`` and its helpers.

Pins every branch the polymorphic ``add_image(source, ...)`` dispatcher walks.
Most branches are pure functions — no DB, no storage, no Pillow. The async
dispatcher itself is tested by calling it on a bare ``HasMedia`` stub.

What it covers:

- Every accepted source: ``TestAcceptedSources::*``
- Every rejection path: ``TestRejectionPaths::*``
- Branch coverage on ``trait.py`` / helpers (verified by report after merge)
- Scheme allowlist (OWASP A05): ``test_unsupported_scheme_rejected_*``
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from arvel_image.media.exceptions import FileTooLargeError, MediaError
from arvel_image.media.trait import (
    HasMedia,
    coerce_sync_source,
    decode_base64,
    is_base64_payload,
    read_from_file_like,
    read_from_path,
)


# Bare HasMedia stub — `coerce_source` never reads `self`, so the cheapest
# possible host is enough. The MRO guard is satisfied because HasMedia is the
# only base class with a to_dict.
class _Host(HasMedia):
    pass


@pytest.fixture
def host() -> _Host:
    return _Host()


@pytest.fixture
def sample_bytes() -> bytes:
    return b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 32


@pytest.fixture
def sample_file(tmp_path: Path, sample_bytes: bytes) -> Path:
    p = tmp_path / "hero.jpg"
    p.write_bytes(sample_bytes)
    return p


# ─── every accepted source returns (bytes, file_name) ───────────────────────


class TestAcceptedSources:
    async def test_bytes_with_file_name(self, host: _Host, sample_bytes: bytes) -> None:
        contents, name = await host.coerce_source(
            sample_bytes, file_name="x.jpg", max_bytes=1_000_000
        )
        assert contents == sample_bytes
        assert name == "x.jpg"
        assert isinstance(contents, bytes)

    async def test_bytearray_with_file_name(self, host: _Host, sample_bytes: bytes) -> None:
        contents, name = await host.coerce_source(
            bytearray(sample_bytes), file_name="x.jpg", max_bytes=1_000_000
        )
        assert contents == sample_bytes
        assert isinstance(contents, bytes), "bytearray must be coerced to bytes"
        assert name == "x.jpg"

    async def test_memoryview_with_file_name(self, host: _Host, sample_bytes: bytes) -> None:
        contents, name = await host.coerce_source(
            memoryview(sample_bytes), file_name="x.jpg", max_bytes=1_000_000
        )
        assert contents == sample_bytes
        assert isinstance(contents, bytes), "memoryview must be coerced to bytes"
        assert name == "x.jpg"

    async def test_str_filesystem_path(self, host: _Host, sample_file: Path) -> None:
        contents, name = await host.coerce_source(
            str(sample_file), file_name=None, max_bytes=1_000_000
        )
        assert contents == sample_file.read_bytes()
        assert name == sample_file.name

    async def test_str_filesystem_path_overrides_file_name(
        self, host: _Host, sample_file: Path
    ) -> None:
        _, name = await host.coerce_source(
            str(sample_file), file_name="override.jpg", max_bytes=1_000_000
        )
        assert name == "override.jpg"

    async def test_pathlike_object(self, host: _Host, sample_file: Path) -> None:
        contents, name = await host.coerce_source(sample_file, file_name=None, max_bytes=1_000_000)
        assert contents == sample_file.read_bytes()
        assert name == sample_file.name

    async def test_data_uri(self, host: _Host, sample_bytes: bytes) -> None:
        payload = base64.b64encode(sample_bytes).decode()
        uri = f"data:image/jpeg;base64,{payload}"
        contents, name = await host.coerce_source(uri, file_name="hero.jpg", max_bytes=1_000_000)
        assert contents == sample_bytes
        assert name == "hero.jpg"

    async def test_bare_base64_payload(self, host: _Host) -> None:
        # 96 raw bytes → 128 chars base64, comfortably above the 64-char threshold.
        raw = b"\x00" * 96
        payload = base64.b64encode(raw).decode()
        assert len(payload) >= 64
        contents, name = await host.coerce_source(
            payload, file_name="blob.bin", max_bytes=1_000_000
        )
        assert contents == raw
        assert name == "blob.bin"

    async def test_file_like_with_read(self, host: _Host, sample_bytes: bytes) -> None:
        import io

        contents, name = await host.coerce_source(
            io.BytesIO(sample_bytes), file_name="stream.jpg", max_bytes=1_000_000
        )
        assert contents == sample_bytes
        assert name == "stream.jpg"


# ─── every rejection path raises a typed error with substring match ─────────


class TestRejectionPaths:
    async def test_bytes_without_file_name(self, host: _Host, sample_bytes: bytes) -> None:
        with pytest.raises(MediaError, match="file_name is required") as exc:
            await host.coerce_source(sample_bytes, file_name=None, max_bytes=1_000_000)
        assert "bytes" in str(exc.value)

    async def test_bytearray_without_file_name(self, host: _Host) -> None:
        with pytest.raises(MediaError, match="file_name is required") as exc:
            await host.coerce_source(bytearray(b"x" * 16), file_name=None, max_bytes=1_000_000)
        assert "bytearray" in str(exc.value)

    async def test_memoryview_without_file_name(self, host: _Host) -> None:
        with pytest.raises(MediaError, match="file_name is required") as exc:
            await host.coerce_source(memoryview(b"x" * 16), file_name=None, max_bytes=1_000_000)
        assert "memoryview" in str(exc.value)

    @pytest.mark.parametrize("scheme", ["file", "ftp", "gopher", "ssh"])
    async def test_unsupported_scheme_rejected(self, host: _Host, scheme: str) -> None:
        with pytest.raises(MediaError, match="Unsupported URL scheme") as exc:
            await host.coerce_source(
                f"{scheme}://example.com/x.jpg", file_name=None, max_bytes=1_000_000
            )
        assert scheme in str(exc.value)
        # Per OWASP A05 (and the security requirement on this story): scheme
        # allowlist short-circuits before read_from_path can ever see it.
        assert "only http and https" in str(exc.value)

    async def test_base64_without_file_name(self, host: _Host) -> None:
        payload = base64.b64encode(b"\x00" * 96).decode()
        with pytest.raises(MediaError, match="file_name is required") as exc:
            await host.coerce_source(payload, file_name=None, max_bytes=1_000_000)
        assert "base64" in str(exc.value)

    async def test_data_uri_without_file_name(self, host: _Host) -> None:
        payload = base64.b64encode(b"\x00" * 96).decode()
        uri = f"data:image/jpeg;base64,{payload}"
        with pytest.raises(MediaError, match="file_name is required"):
            await host.coerce_source(uri, file_name=None, max_bytes=1_000_000)

    async def test_base64_with_invalid_chars(self, host: _Host) -> None:
        # data: URI bypasses the is_base64_payload heuristic and goes straight
        # to decode_base64, so we can throw any garbage at it.
        uri = "data:image/jpeg;base64,!!not-valid base64!!"
        with pytest.raises(MediaError, match="Invalid base64") as exc:
            await host.coerce_source(uri, file_name="x.jpg", max_bytes=1_000_000)
        assert "encoded chars" in str(exc.value)

    async def test_base64_oversize_raises_file_too_large(self, host: _Host) -> None:
        raw = b"\x00" * 512
        payload = base64.b64encode(raw).decode()
        uri = f"data:application/octet-stream;base64,{payload}"
        with pytest.raises(FileTooLargeError, match="Decoded base64") as exc:
            await host.coerce_source(uri, file_name="x.bin", max_bytes=100)
        assert "512 bytes" in str(exc.value)
        assert "max_bytes=100" in str(exc.value)

    async def test_unreadable_filesystem_path(self, host: _Host, tmp_path: Path) -> None:
        missing = tmp_path / "does-not-exist.jpg"
        with pytest.raises(MediaError, match="Could not read media") as exc:
            await host.coerce_source(str(missing), file_name=None, max_bytes=1_000_000)
        assert str(missing) in str(exc.value)

    async def test_file_like_without_file_name(self, host: _Host) -> None:
        import io

        with pytest.raises(MediaError, match="file_name is required") as exc:
            await host.coerce_source(io.BytesIO(b"\x00" * 16), file_name=None, max_bytes=1_000_000)
        assert "file-like" in str(exc.value)

    async def test_unsupported_source_type(self, host: _Host) -> None:
        with pytest.raises(MediaError, match="Unsupported media source type") as exc:
            await host.coerce_source(42, file_name="x.jpg", max_bytes=1_000_000)  # type: ignore[arg-type]
        assert "int" in str(exc.value)


# ─── Pure-helper coverage ────────────────────────────────────────────────────


class TestReadFromFileLike:
    def test_string_payload_is_encoded_to_bytes(self) -> None:
        import io

        contents, name = read_from_file_like(io.StringIO("hello"), "x.txt")
        assert contents == b"hello"
        assert name == "x.txt"

    def test_bytearray_payload_is_coerced_to_bytes(self) -> None:
        class _Src:
            def read(self) -> bytearray:
                return bytearray(b"abc")

        contents, name = read_from_file_like(_Src(), "x.bin")
        assert contents == b"abc"
        assert isinstance(contents, bytes)
        assert name == "x.bin"

    def test_memoryview_payload_is_coerced_to_bytes(self) -> None:
        class _Src:
            def read(self) -> memoryview:
                return memoryview(b"abc")

        contents, _ = read_from_file_like(_Src(), "x.bin")
        assert contents == b"abc"
        assert isinstance(contents, bytes)

    def test_unsupported_read_return_type_raises(self) -> None:
        class _Src:
            def read(self) -> list[int]:
                return [1, 2, 3]

        with pytest.raises(MediaError, match="returned list") as exc:
            read_from_file_like(_Src(), "x.bin")
        assert "_Src" in str(exc.value)


class TestReadFromPath:
    def test_pathlike_input_works(self, sample_file: Path) -> None:
        contents, name = read_from_path(sample_file, None)
        assert contents == sample_file.read_bytes()
        assert name == sample_file.name

    def test_explicit_file_name_overrides_basename(self, sample_file: Path) -> None:
        _, name = read_from_path(sample_file, "custom.png")
        assert name == "custom.png"

    def test_os_error_is_wrapped(self, tmp_path: Path) -> None:
        missing = tmp_path / "ghost.jpg"
        with pytest.raises(MediaError, match="Could not read media from") as exc:
            read_from_path(missing, None)
        assert isinstance(exc.value.__cause__, OSError)


class TestDecodeBase64:
    def test_without_file_name_rejected(self) -> None:
        payload = base64.b64encode(b"\x00" * 64).decode()
        with pytest.raises(MediaError, match="file_name is required"):
            decode_base64(payload, file_name=None, max_bytes=1_000)

    def test_oversize_payload_raises_file_too_large(self) -> None:
        raw = b"\x00" * 200
        payload = base64.b64encode(raw).decode()
        with pytest.raises(FileTooLargeError) as exc:
            decode_base64(payload, file_name="x.bin", max_bytes=50)
        # Error names both the actual and configured caps.
        assert "200 bytes" in str(exc.value)
        assert "max_bytes=50" in str(exc.value)


class TestIsBase64Payload:
    @pytest.mark.parametrize(
        "value",
        [
            "",
            "abc",  # below threshold
            "abcd" * 15 + "abc",  # not multiple of 4
            "abcd" * 16 + "!@",  # right length, wrong charset
        ],
    )
    def test_rejects_non_base64(self, value: str) -> None:
        assert is_base64_payload(value) is False

    def test_accepts_real_payload(self) -> None:
        payload = base64.b64encode(b"\x00" * 96).decode()
        assert is_base64_payload(payload) is True


# ─── coerce_sync_source (image_builder's gate) ─────────────────────────────


class TestCoerceSyncSource:
    def test_bytes_without_file_name_rejected(self, sample_bytes: bytes) -> None:
        with pytest.raises(MediaError, match="file_name is required") as exc:
            coerce_sync_source(sample_bytes, None)
        assert "bytes" in str(exc.value)

    def test_bytearray_round_trips(self, sample_bytes: bytes) -> None:
        contents, name = coerce_sync_source(bytearray(sample_bytes), "x.jpg")
        assert contents == sample_bytes
        assert isinstance(contents, bytes)
        assert name == "x.jpg"

    def test_str_path_reads_file(self, sample_file: Path) -> None:
        contents, name = coerce_sync_source(str(sample_file), None)
        assert contents == sample_file.read_bytes()
        assert name == sample_file.name

    def test_pathlike_reads_file(self, sample_file: Path) -> None:
        contents, _ = coerce_sync_source(sample_file, None)
        assert contents == sample_file.read_bytes()

    def test_file_like_with_read(self, sample_bytes: bytes) -> None:
        import io

        contents, name = coerce_sync_source(io.BytesIO(sample_bytes), "stream.jpg")
        assert contents == sample_bytes
        assert name == "stream.jpg"

    def test_unsupported_type_rejected(self) -> None:
        with pytest.raises(MediaError, match="image_builder accepts") as exc:
            coerce_sync_source(42, "x.jpg")  # type: ignore[arg-type]
        assert "Use add_image() directly for URLs" in str(exc.value)


# ─── coerce_source URL branch — mocked at fetch_url to keep the test offline


class TestUrlBranch:
    async def test_http_url_routes_to_url_fetcher(
        self, host: _Host, sample_bytes: bytes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel_image.media import url_fetcher

        seen: dict[str, object] = {}

        async def _fake_fetch(url: str, *, max_bytes: int) -> tuple[bytes, str]:
            seen["url"] = url
            seen["max_bytes"] = max_bytes
            return sample_bytes, "remote.jpg"

        monkeypatch.setattr(url_fetcher, "fetch_url", _fake_fetch)

        contents, name = await host.coerce_source(
            "https://cdn.example.com/img.jpg", file_name=None, max_bytes=999
        )
        assert contents == sample_bytes
        assert name == "remote.jpg"
        assert seen == {"url": "https://cdn.example.com/img.jpg", "max_bytes": 999}

    async def test_http_url_caller_file_name_overrides_derived(
        self, host: _Host, sample_bytes: bytes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from arvel_image.media import url_fetcher

        async def _fake_fetch(url: str, *, max_bytes: int) -> tuple[bytes, str]:
            del url, max_bytes
            return sample_bytes, "remote.jpg"

        monkeypatch.setattr(url_fetcher, "fetch_url", _fake_fetch)

        _, name = await host.coerce_source(
            "https://cdn.example.com/img.jpg",
            file_name="caller-wins.jpg",
            max_bytes=999,
        )
        assert name == "caller-wins.jpg"
