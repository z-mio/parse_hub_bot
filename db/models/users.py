from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base

if TYPE_CHECKING:
    from db.models.user_settings import UserSettings


class Users(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)

    language_code: Mapped[str] = mapped_column(String(16), nullable=False, default="zh-hans", server_default="zh-hans")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    settings: Mapped[UserSettings | None] = relationship(
        "UserSettings",
        back_populates="user",
        cascade="all, delete-orphan",
        single_parent=True,
        uselist=False,
    )
