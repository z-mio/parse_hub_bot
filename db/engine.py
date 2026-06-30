from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine

from core.config import bs

engine = create_async_engine(bs.database_url)


@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection: Any, connection_record: Any) -> None:
    if engine.url.get_backend_name() != "sqlite":
        return

    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
    finally:
        cursor.close()


async def close_db() -> None:
    await engine.dispose()
