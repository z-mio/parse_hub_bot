from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db.engine import engine

async_session = async_sessionmaker(bind=engine, expire_on_commit=False)


@asynccontextmanager
async def get_session_context() -> AsyncGenerator[AsyncSession]:
    session = async_session()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession]:
    async with get_session_context() as session:
        yield session
