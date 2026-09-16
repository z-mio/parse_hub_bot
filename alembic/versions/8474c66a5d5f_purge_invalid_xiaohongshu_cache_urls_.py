"""purge invalid xiaohongshu cache urls again

Revision ID: 8474c66a5d5f
Revises: 9478f8c31350
Create Date: 2026-09-16 11:17:05.878407

"""

import logging
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

logger = logging.getLogger("alembic.runtime.migration")
# revision identifiers, used by Alembic.
revision: str = "8474c66a5d5f"
down_revision: str | Sequence[str] | None = "9478f8c31350"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


INVALID_URLS: tuple[str, ...] = ("https://www.xiaohongshu.com/login",)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 新数据库还没有 cache 表, 无需清理。
    if not inspector.has_table("cache"):
        return

    metadata = sa.MetaData()
    cache = sa.Table("cache", metadata, autoload_with=bind)
    result = bind.execute(cache.delete().where(cache.c.url.in_(INVALID_URLS)))
    logger.info(f"已清理 {result.rowcount} 条无效缓存")


def downgrade() -> None:
    """Downgrade schema."""
    raise NotImplementedError("无效缓存 URL 已删除, 该迁移无法安全降级。请从数据库备份恢复。")
