import asyncio
import time
from enum import Enum
from typing import Any

from pickledb import PickleDB
from pydantic import BaseModel

from core.config import bs
from log import logger


class TTLCache:
    def __init__(self, ttl: float = 300):
        self._ttl = ttl
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = asyncio.Lock()
        self.logger = logger.bind(name="TTLCache")

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self.logger.debug(f"缓存未命中: key={key}")
                return None
            value, expire_at = entry
            if time.monotonic() > expire_at:
                self.logger.debug(f"缓存已过期: key={key}")
                del self._store[key]
                return None
            self.logger.debug(f"缓存命中: key={key}")
            return value

    async def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        async with self._lock:
            effective_ttl = ttl or self._ttl
            self.logger.debug(f"缓存写入: key={key}, ttl={effective_ttl}s")
            self._store[key] = (value, time.monotonic() + effective_ttl)

    async def pop(self, key: str) -> Any | None:
        async with self._lock:
            entry = self._store.pop(key, None)
            if entry is None:
                self.logger.debug(f"缓存 pop 未命中: key={key}")
                return None
            value, expire_at = entry
            if time.monotonic() > expire_at:
                self.logger.debug(f"缓存 pop 已过期: key={key}")
                return None
            self.logger.debug(f"缓存 pop 命中: key={key}")
            return value


class CacheMediaType(str, Enum):
    PHOTO = "photo"
    VIDEO = "video"
    ANIMATION = "animation"
    DOCUMENT = "document"


class CacheParseResult(BaseModel):
    title: str = ""
    content: str = ""


class CacheMedia(BaseModel):
    type: CacheMediaType
    file_id: str
    cover_file_id: str | None = None


class CacheEntry(BaseModel):
    parse_result: CacheParseResult | None = None
    media: list[CacheMedia | list[CacheMedia]] | None = None
    telegraph_url: str | None = None


class FileIdCache:
    def __init__(self, db_path: str):
        self._db = PickleDB(db_path)
        self.logger = logger.bind(name="FileIdCache")
        self.logger.debug(f"file_id 持久化缓存已加载: {db_path}")

    async def get(self, url: str) -> CacheEntry | None:
        async with self._db as db:
            data = await db.get(url)
        if data is None:
            return None
        self.logger.debug(f"file_id 缓存命中: key={url} value={data}")
        return CacheEntry.model_validate(data)

    async def set(self, url: str, entry: CacheEntry) -> None:
        async with self._db as db:
            await db.set(url, entry.model_dump())
            self.logger.debug(f"file_id 缓存写入: key={url} value={entry}")

    async def remove(self, url: str) -> None:
        async with self._db as db:
            await db.remove(url)


parse_cache = TTLCache(ttl=300)
file_id_cache = FileIdCache(bs.data_path / "cache.json")
