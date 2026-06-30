from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, func
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base

if TYPE_CHECKING:
    from db.models.users import Users


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    settings_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON),
        nullable=False,
        default=dict,
    )
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[Users] = relationship("Users", back_populates="settings")

    __mapper_args__ = {"version_id_col": lock_version}
