"""Media ORM model — stores file metadata and model associations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import mapped_column

from arvel.data.model import ArvelModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Mapped


class MediaItem(ArvelModel):
    """A file associated with a model through a named collection.

    Columns classified as ``internal`` — no PII stored directly. File
    content lives on the storage disk; this table stores metadata only.
    """

    __tablename__ = "media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), nullable=False, default="", index=True)
    model_type: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    model_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )
    collection: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="default",
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    disk: Mapped[str] = mapped_column(String(50), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    conversions: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
    )
    custom_properties: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
    )
    order_column: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
