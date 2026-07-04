"""HTTP-PARITY §2 — the fluent ``response()`` builder: json/no_content/download/file/stream,
and ``Response.with_cookie``/``without_cookie`` applied by the kernel's conversion funnel."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from litestar.testing import TestClient

from arvel.http import HttpKernel, Response
from arvel.http.response import FileDownload, StreamValue, response


def test_response_call_builds_a_plain_response() -> None:
    r = response("hi", 201, headers={"x-a": "1"})
    assert r.content == "hi" and r.status == 201 and r.headers == {"x-a": "1"}


def test_response_json_sets_content_and_status() -> None:
    r = response.json({"ok": True}, 201)
    assert isinstance(r, Response)
    assert r.content == {"ok": True} and r.status == 201


def test_response_no_content_is_204() -> None:
    r = response.no_content()
    assert r.status == 204 and r.content is None


def test_download_and_file_build_file_download_value_objects(tmp_path: Path) -> None:
    target = tmp_path / "x.txt"
    d = response.download(target, name="report.txt")
    assert isinstance(d, FileDownload)
    assert d.name == "report.txt" and d.inline is False

    f = response.file(target)
    assert isinstance(f, FileDownload)
    assert f.inline is True


def test_stream_builds_stream_value() -> None:
    async def gen() -> Any:
        yield b"a"

    s = response.stream(gen(), media_type="text/plain")
    assert isinstance(s, StreamValue)
    assert s.media_type == "text/plain"


# --- served through the kernel funnel ---------------------------------------------------------


def test_download_served_with_content_disposition(tmp_path: Path) -> None:
    target = tmp_path / "report.txt"
    target.write_text("hello world")

    kernel = HttpKernel()
    kernel.get("/dl", lambda request: response.download(target, name="report.txt"))
    with TestClient(kernel.build()) as client:
        resp = client.get("/dl")
    assert resp.status_code == 200
    assert resp.text == "hello world"
    disposition = resp.headers["content-disposition"]
    assert "attachment" in disposition and "report.txt" in disposition


def test_file_served_inline(tmp_path: Path) -> None:
    target = tmp_path / "view.txt"
    target.write_text("inline body")

    kernel = HttpKernel()
    kernel.get("/view", lambda request: response.file(target))
    with TestClient(kernel.build()) as client:
        resp = client.get("/view")
    assert resp.status_code == 200
    assert resp.text == "inline body"
    assert "inline" in resp.headers["content-disposition"]


def test_stream_served_as_chunked_body() -> None:
    async def gen() -> Any:
        yield b"chunk-1-"
        yield b"chunk-2"

    kernel = HttpKernel()
    kernel.get("/stream", lambda request: response.stream(gen(), media_type="text/plain"))
    with TestClient(kernel.build()) as client:
        resp = client.get("/stream")
    assert resp.status_code == 200
    assert resp.text == "chunk-1-chunk-2"
    assert resp.headers["content-type"].startswith("text/plain")


# --- cookies -----------------------------------------------------------------------------------


def test_with_cookie_is_applied_to_the_served_response() -> None:
    def handler(request: Any) -> Response:
        return response.json({"ok": True}).with_cookie("prefs", "dark", minutes=60, secure=False)

    kernel = HttpKernel()
    kernel.get("/c", handler)
    with TestClient(kernel.build()) as client:
        resp = client.get("/c")
    assert resp.cookies["prefs"] == "dark"
    set_cookie = resp.headers["set-cookie"]
    assert "Max-Age=3600" in set_cookie


def test_without_cookie_expires_it() -> None:
    def handler(request: Any) -> Response:
        return response.json({"ok": True}).without_cookie("prefs")

    kernel = HttpKernel()
    kernel.get("/c", handler)
    with TestClient(kernel.build()) as client:
        resp = client.get("/c")
    set_cookie = resp.headers["set-cookie"]
    assert "prefs=" in set_cookie
    assert ("Max-Age=0" in set_cookie) or ("1970" in set_cookie)  # an expired/deleted cookie


def test_host_prefixed_cookie_forces_path_and_no_domain() -> None:
    def handler(request: Any) -> Response:
        return response.json({"ok": True}).with_cookie(
            "__Host-x", "v", secure=True, path="/other", domain="example.com"
        )

    kernel = HttpKernel()
    kernel.get("/c", handler)
    with TestClient(kernel.build()) as client:
        resp = client.get("/c")
    set_cookie = resp.headers["set-cookie"]
    assert "Path=/" in set_cookie
    assert "Domain=" not in set_cookie
