from alembic.config import Config
from sqlalchemy.engine import Connection

import db.models  # noqa: F401
from alembic import command
from db.base import Base
from db.session import engine


def stamp_head(connection: Connection) -> None:
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.attributes["connection"] = connection
    command.stamp(alembic_cfg, "head")


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(stamp_head)
