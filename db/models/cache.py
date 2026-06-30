from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class Cache(Base):
    __tablename__ = "cache"
    __table_args__ = (Index("ix_cache_lru", "accessed_at", "updated_at", "created_at"),)

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    entry_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    accessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
