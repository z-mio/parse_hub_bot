import asyncio
import hashlib
import time
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from core import bs
from db import get_session
from log import logger
from repo.cache import CacheRepo


class TTLCache:
    def __init__(self, ttl: float = 300, cleanup_interval: float = 60, maxsize: int = 0):
        self._ttl = ttl
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = asyncio.Lock()
        self.logger = logger.bind(name="TTLCache")
        self._cleanup_interval = cleanup_interval
        self._cleanup_task: asyncio.Task | None = None
        self._maxsize = maxsize

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
            if key in self._store:
                del self._store[key]
            self._store[key] = (value, time.monotonic() + effective_ttl)
            await self._evict_overflow_locked()

    async def _evict_overflow_locked(self) -> None:
        if self._maxsize <= 0:
            return
        overflow = len(self._store) - self._maxsize
        if overflow <= 0:
            return
        for key in list(self._store)[:overflow]:
            del self._store[key]
        self.logger.debug(f"缓存数量超限, 淘汰最旧缓存: {overflow} 条")

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

    def start_cleanup(self) -> None:
        """启动后台清理任务（需在事件循环运行后调用）"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
            self.logger.debug(f"后台清理任务已启动, interval={self._cleanup_interval}s")

    async def _periodic_cleanup(self) -> None:
        while True:
            await asyncio.sleep(self._cleanup_interval)
            async with self._lock:
                now = time.monotonic()
                expired_keys = [k for k, (_, exp) in self._store.items() if now > exp]
                for k in expired_keys:
                    del self._store[k]
                if expired_keys:
                    self.logger.debug(f"定时清理过期缓存: {len(expired_keys)} 条")


class CacheMediaType(StrEnum):
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


class PersistentCache:
    def __init__(
        self,
        max_entries: int = 30000,
        stale_after: timedelta = timedelta(days=7),
        evict_batch_size: int = 100,
    ):
        self.logger = logger.bind(name="PersistentCache")
        self.logger.debug("数据库缓存已初始化")
        self._max_entries = max_entries
        self._stale_after = stale_after
        self._evict_batch_size = evict_batch_size

    @staticmethod
    def _make_key(url: str) -> str:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    async def get(self, url: str) -> CacheEntry | None:
        key = self._make_key(url)
        async with get_session() as session:
            repo = CacheRepo(session)
            cache = await repo.get(key)
            if cache is None:
                self.logger.debug(f"缓存未命中: key={url}")
                return None

            try:
                entry: CacheEntry = CacheEntry.model_validate(cache.entry_json)
            except Exception as e:
                self.logger.warning(f"缓存内容无效, 已删除: key={url}, error={e}")
                await repo.remove(cache)
                return None

            await repo.touch(cache, self._now())
            self.logger.debug(f"缓存命中: key={url}")
            return entry

    async def set(self, url: str, entry: CacheEntry) -> None:
        key = self._make_key(url)
        now = self._now()
        async with get_session() as session:
            repo = CacheRepo(session)
            await repo.upsert(key=key, url=url, entry_json=entry.model_dump(mode="json"), accessed_at=now)
            removed = await self._evict_overflow(repo)
            self.logger.debug(f"缓存写入: key={url}, evicted={removed}")

    async def remove(self, url: str) -> None:
        key = self._make_key(url)
        async with get_session() as session:
            await CacheRepo(session).remove_by_key(key)

    async def _evict_overflow(self, repo: CacheRepo) -> int:
        if self._max_entries <= 0:
            return 0

        count = await repo.count()
        if count <= self._max_entries:
            return 0

        removed = await repo.remove_stale(self._now() - self._stale_after)
        count -= removed
        overflow = count - self._max_entries
        if overflow <= 0:
            return removed

        return removed + await repo.remove_oldest(max(overflow, self._evict_batch_size))


parse_cache = TTLCache(ttl=30 * 60, maxsize=1000)  # 解析结果缓存 30 分钟
persistent_cache = PersistentCache(max_entries=bs.cache_max_entries)
