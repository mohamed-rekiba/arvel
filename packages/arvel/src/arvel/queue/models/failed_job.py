"""FailedJob ORM model (maps to the `failed_jobs` table)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Column, DateTime, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase


class FailedJobBase(DeclarativeBase):
    pass


class FailedJob(FailedJobBase):
    """Represents one row in the `failed_jobs` dead-letter table."""

    __tablename__ = "failed_jobs"

    id: Any = Column(Integer, primary_key=True, autoincrement=True)
    uuid: Any = Column(String(36), nullable=False, unique=True)
    queue: Any = Column(String(255), nullable=False)
    payload: Any = Column(Text, nullable=False)
    error: Any = Column(Text, nullable=False)
    failed_at: Any = Column(DateTime, nullable=False, server_default=func.now())

    def __repr__(self) -> str:
        return f"<FailedJob uuid={self.uuid!r} queue={self.queue!r}>"


__all__ = ["FailedJob"]
