"""WI-arvel-074 — Epic 049 Story 14: exists/unique/mimes/dimensions validation rules."""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from typing import Any

from arvel.database import Model
from arvel.http.exceptions import HttpExceptionHandler
from arvel.http.requests import FormRequest
from arvel.routing import Route, Router
from arvel.validation import Validator
from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import Integer, String
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from starlette.testclient import TestClient


class Wi074Post(Model):
    __tablename__ = "wi074_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    email: Mapped[str] = mapped_column(String(200), nullable=False)


async def _setup(engine: AsyncEngine, session: AsyncSession) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)
    session.add(Wi074Post(email="taken@example.com"))
    await session.flush()


def _png(width: int, height: int) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IEND", b"")


def _jpeg(width: int, height: int) -> bytes:
    segment = (
        b"\xff\xc0"
        + (8).to_bytes(2, "big")
        + b"\x08"
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
        + b"\x03"
    )
    return b"\xff\xd8" + segment + b"\xff\xd9"


@dataclass(slots=True)
class _FakeUpload:
    content_type: str | None
    filename: str | None
    data: bytes

    def read(self) -> bytes:
        return self.data


class TestExistsRule:
    async def test_ignores_none_values(self) -> None:
        details = await Validator({"post_id": None}).validate({"post_id": "exists:posts,id"})
        assert details == []

    async def test_requires_table_and_column_parameters(self) -> None:
        details = await Validator({"post_id": 1}).validate({"post_id": "exists:posts"})
        assert details[0]["issue"] == "The post_id rule exists requires table and column."

    async def test_passes_when_row_exists(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine, session)
        post = await Wi074Post.create(email="other@example.com")
        details = await Validator({"post_id": post.id}).validate(
            {"post_id": "exists:wi074_posts,id"}
        )
        assert details == []

    async def test_fails_when_row_missing(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine, session)
        details = await Validator({"post_id": 999}).validate({"post_id": "exists:wi074_posts,id"})
        assert len(details) == 1
        assert details[0]["field"] == "post_id"


class TestUniqueRule:
    async def test_ignores_none_values(self) -> None:
        details = await Validator({"email": None}).validate({"email": "unique:users,email"})
        assert details == []

    async def test_requires_table_and_column_parameters(self) -> None:
        details = await Validator({"email": "a@example.com"}).validate({"email": "unique:users"})
        assert details[0]["issue"] == "The email rule unique requires table and column."

    async def test_fails_on_duplicate_email(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine, session)
        details = await Validator({"email": "taken@example.com"}).validate(
            {"email": "unique:wi074_posts,email"}
        )
        assert len(details) == 1
        assert "taken" in details[0]["issue"]

    async def test_except_allows_same_record_on_update(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine, session)
        post = await Wi074Post.create(email="free@example.com")
        details = await Validator({"email": "free@example.com"}).validate(
            {"email": f"unique:wi074_posts,email,{post.id},id"}
        )
        assert details == []


class TestMimesRule:
    async def test_ignores_none_values(self) -> None:
        details = await Validator({"avatar": None}).validate({"avatar": "mimes:png"})
        assert details == []

    async def test_requires_extensions(self) -> None:
        details = await Validator({"avatar": "photo.png"}).validate({"avatar": "mimes"})
        assert details[0]["issue"] == "The avatar rule mimes requires at least one extension."

    async def test_accepts_matching_filename_without_upload_object(self) -> None:
        details = await Validator({"avatar": "photo.jpg"}).validate({"avatar": "mimes:jpg"})
        assert details == []

    async def test_accepts_matching_content_type_without_extension(self) -> None:
        upload = _FakeUpload("image/png", "photo", b"data")
        details = await Validator({"avatar": upload}).validate({"avatar": "mimes:png"})
        assert details == []

    async def test_accepts_matching_extension_and_mime(self) -> None:
        upload = _FakeUpload("image/png", "photo.png", b"data")
        details = await Validator({"avatar": upload}).validate({"avatar": "mimes:png,jpg"})
        assert details == []

    async def test_rejects_wrong_extension(self) -> None:
        upload = _FakeUpload("application/pdf", "doc.pdf", b"data")
        details = await Validator({"avatar": upload}).validate({"avatar": "mimes:png,jpg"})
        assert len(details) == 1


class TestDimensionsRule:
    async def test_ignores_none_values(self) -> None:
        details = await Validator({"photo": None}).validate({"photo": "dimensions:width=10"})
        assert details == []

    async def test_rejects_non_image_values(self) -> None:
        details = await Validator({"photo": object()}).validate({"photo": "dimensions:width=10"})
        assert details[0]["issue"] == "The photo must be an image."

    async def test_reports_invalid_dimension_parameter(self) -> None:
        details = await Validator({"photo": _png(10, 10)}).validate({"photo": "dimensions:width"})
        assert "Invalid dimensions parameter" in details[0]["issue"]

    async def test_rejects_non_matching_exact_dimensions(self) -> None:
        details = await Validator({"photo": memoryview(_png(10, 20))}).validate(
            {"photo": "dimensions:width=9,height=20"}
        )
        assert details[0]["issue"] == "The photo must be exactly 9 pixels wide."

    async def test_reads_async_file_like_upload(self) -> None:
        class Upload:
            async def read(self) -> bytes:
                return _png(12, 12)

        details = await Validator({"photo": Upload()}).validate({"photo": "dimensions:width=12"})
        assert details == []

    async def test_parses_jpeg_dimensions(self) -> None:
        details = await Validator({"photo": _jpeg(32, 16)}).validate(
            {"photo": "dimensions:width=32,height=16"}
        )
        assert details == []

    async def test_passes_when_image_meets_minimums(self) -> None:
        image = _png(120, 80)
        details = await Validator({"photo": image}).validate(
            {"photo": "dimensions:min_width=100,min_height=50"}
        )
        assert details == []

    async def test_fails_when_image_too_small(self) -> None:
        image = _png(50, 50)
        details = await Validator({"photo": image}).validate(
            {"photo": "dimensions:min_width=100,min_height=100"}
        )
        assert len(details) == 1
        assert "100" in details[0]["issue"]


class TestFormRequestRulesIntegration:
    async def test_unique_rule_returns_422(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine, session)
        Router.reset_singleton()

        class Payload(BaseModel):
            email: str

        class StoreEmail(FormRequest[Payload]):
            async def authorize(self, request: Any) -> bool:
                return True

            def rules(self) -> dict[str, str | list[str]]:
                return {"email": "unique:wi074_posts,email"}

            def messages(self) -> dict[str, str]:
                return {"email.unique": "That email is already taken."}

        @Route.post("/emails")
        async def store(form: StoreEmail) -> dict[str, str]:
            return {"email": form.validated().email}

        del store
        app = FastAPI()
        HttpExceptionHandler().register(app)
        Router.singleton().register_with_app(app)

        resp = TestClient(app).post("/emails", json={"email": "taken@example.com"})
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "VALIDATION_FAILED"
        assert body["error"]["details"][0]["issue"] == "That email is already taken."

    async def test_rules_run_before_authorize(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine, session)
        Router.reset_singleton()

        class Payload(BaseModel):
            email: str

        class StoreEmail(FormRequest[Payload]):
            async def authorize(self, request: Any) -> bool:
                return False

            def rules(self) -> dict[str, str | list[str]]:
                return {"email": "unique:wi074_posts,email"}

        @Route.post("/emails")
        async def store(form: StoreEmail) -> dict[str, str]:
            return {"email": form.validated().email}

        del store
        app = FastAPI()
        HttpExceptionHandler().register(app)
        Router.singleton().register_with_app(app)

        resp = TestClient(app).post("/emails", json={"email": "taken@example.com"})
        assert resp.status_code == 422
