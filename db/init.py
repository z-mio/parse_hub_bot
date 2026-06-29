import logging

from alembic.config import Config
from sqlalchemy.engine import Connection

import db.models  # noqa: F401
from alembic import command
from db.base import Base
from db.session import engine

ALEMBIC_LOGGERS = (
    "alembic",
    "alembic.runtime.migration",
)


def stamp_head(connection: Connection) -> None:
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.attributes["connection"] = connection
    alembic_cfg.attributes["skip_logging_config"] = True

    logger_levels = {name: logging.getLogger(name).level for name in ALEMBIC_LOGGERS}
    try:
        for name in ALEMBIC_LOGGERS:
            logging.getLogger(name).setLevel(logging.WARNING)
        command.stamp(alembic_cfg, "head")
    finally:
        for name, level in logger_levels.items():
            logging.getLogger(name).setLevel(level)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(stamp_head)
