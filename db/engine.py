from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = "sqlite+aiosqlite:///data/db/database.db"

engine = create_async_engine(DATABASE_URL, connect_args={"autocommit": False})


@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection: Any, connection_record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


async def close_db() -> None:
    await engine.dispose()
