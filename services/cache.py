import asyncio
import time
from enum import Enum
from typing import Any

from pickledb import PickleDB
from pydantic import BaseModel

from core import bs
from log import logger


class TTLCache:
    def __init__(self, ttl: float = 300, cleanup_interval: float = 60):
        self._ttl = ttl
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = asyncio.Lock()
        self.logger = logger.bind(name="TTLCache")
        self._cleanup_interval = cleanup_interval
        self._cleanup_task: asyncio.Task | None = None

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

    def start_cleanup(self):
        """启动后台清理任务（需在事件循环运行后调用）"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
            self.logger.debug(f"后台清理任务已启动, interval={self._cleanup_interval}s")

    async def _periodic_cleanup(self):
        while True:
            await asyncio.sleep(self._cleanup_interval)
            async with self._lock:
                now = time.monotonic()
                expired_keys = [k for k, (_, exp) in self._store.items() if now > exp]
                for k in expired_keys:
                    del self._store[k]
                if expired_keys:
                    self.logger.debug(f"定时清理过期缓存: {len(expired_keys)} 条")


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
    media: list[CacheMedia] | None = None
    telegraph_url: str | None = None


class _StorageWrapper(BaseModel):
    entry: CacheEntry
    exp: int = 0


class PersistentCache:
    def __init__(self, db_path: str, ttl: int | None = None, cleanup_interval: float = 60):
        self._db = PickleDB(db_path)
        self._ttl = ttl
        self.logger = logger.bind(name="PersistentCache")
        self.logger.debug(f"缓存已加载: {db_path}")
        self._cleanup_interval = cleanup_interval
        self._cleanup_task: asyncio.Task | None = None

    async def get(self, url: str) -> CacheEntry | None:
        async with self._db as db:
            data = await db.get(url)
            if data is None:
                return None

            if (ttl := data.get("exp", 0)) and time.time() > ttl:
                self.logger.debug(f"缓存过期: key={url}")
                await db.remove(url)
                return None
            self.logger.debug(f"缓存命中: key={url} value={data}")
            return _StorageWrapper.model_validate(data).entry

    async def set(self, url: str, entry: CacheEntry) -> None:
        sw = _StorageWrapper(entry=entry, exp=int(time.time() + self._ttl) if self._ttl else 0)
        async with self._db as db:
            await db.set(url, sw.model_dump())
            self.logger.debug(f"缓存写入: key={url} value={sw}")

    async def remove(self, url: str) -> None:
        async with self._db as db:
            await db.remove(url)

    def start_cleanup(self):
        """启动后台清理任务"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
            self.logger.debug(f"后台清理任务已启动, interval={self._cleanup_interval}s")

    async def _periodic_cleanup(self):
        while True:
            await asyncio.sleep(self._cleanup_interval)
            now = time.time()
            removed = 0
            async with self._db as db:
                all_keys = await db.all()
                for key in all_keys:
                    data = await db.get(key)
                    if data and data.get("exp", 0) and now > data["exp"]:
                        await db.remove(key)
                        removed += 1
            if removed:
                self.logger.debug(f"定时清理过期缓存: {removed} 条")


parse_cache = TTLCache(ttl=60 * 60)  # 解析结果缓存 1 小时
persistent_cache = PersistentCache(bs.cache_path / "cache.json", ttl=bs.cache_time)
