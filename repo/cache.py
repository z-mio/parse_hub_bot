from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.cache import Cache


class CacheRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, key: str) -> Cache | None:
        cache = await self._session.scalar(select(Cache).where(Cache.key == key))
        return cache

    async def upsert(self, *, key: str, url: str, entry_json: dict[str, Any], accessed_at: datetime) -> Cache:
        cache = await self.get(key)
        if cache is None:
            cache = Cache(
                key=key,
                url=url,
                entry_json=entry_json,
                accessed_at=accessed_at,
            )
            self._session.add(cache)
            return cache

        cache.url = url
        cache.entry_json = entry_json
        cache.accessed_at = accessed_at
        return cache

    @staticmethod
    async def touch(cache: Cache, accessed_at: datetime) -> None:
        cache.accessed_at = accessed_at

    async def remove(self, cache: Cache) -> None:
        await self._session.delete(cache)

    async def remove_by_key(self, key: str) -> None:
        cache = await self.get(key)
        if cache is not None:
            await self.remove(cache)

    async def count(self) -> int:
        count = await self._session.scalar(select(func.count()).select_from(Cache))
        return count or 0

    async def remove_stale(self, stale_before: datetime) -> int:
        keys = await self._session.scalars(select(Cache.key).where(Cache.accessed_at < stale_before))
        return await self.remove_by_keys(list(keys.all()))

    async def remove_oldest(self, limit: int) -> int:
        keys = await self._session.scalars(
            select(Cache.key).order_by(Cache.accessed_at, Cache.updated_at, Cache.created_at).limit(limit)
        )
        return await self.remove_by_keys(list(keys.all()))

    async def remove_by_keys(self, keys: list[str]) -> int:
        if not keys:
            return 0
        await self._session.execute(delete(Cache).where(Cache.key.in_(keys)))
        return len(keys)
