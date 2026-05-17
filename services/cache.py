import asyncio
import time
from enum import StrEnum
from typing import Any

from pickledb import PickleDB
from pydantic import BaseModel

from core import bs
from log import logger


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


class _StorageWrapper(BaseModel):
    entry: CacheEntry
    exp: int = 0


class PersistentCache:
    def __init__(
        self,
        db_path: str,
        ttl: int,
        save_interval: float = 5 * 60,
        cleanup_interval: float = 60 * 60,
        max_entries: int = 30000,
    ):
        self._db = PickleDB(db_path)
        self._ttl = ttl
        self.logger = logger.bind(name="PersistentCache")
        self.logger.debug(f"缓存已初始化: {db_path}")
        self._save_interval = save_interval
        self._cleanup_interval = cleanup_interval
        self._max_entries = max_entries
        self._cleanup_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._loaded = False
        self._dirty = False
        self._last_cleanup_at = 0.0

    @property
    def enabled(self) -> bool:
        return self._ttl > 0

    async def _ensure_loaded_locked(self) -> None:
        if self._loaded:
            return
        await self._db.load()
        self._loaded = True
        self._last_cleanup_at = time.monotonic()
        removed = await self._evict_overflow_locked()
        if removed:
            self._dirty = True
        self.logger.debug(f"缓存已加载: {self._db.location}, evicted={removed}")

    async def _save_locked(self) -> None:
        if not self._loaded or not self._dirty:
            return
        await self._db.save()
        self._dirty = False
        self.logger.debug("缓存已保存")

    async def get(self, url: str) -> CacheEntry | None:
        if not self.enabled:
            return None
        async with self._lock:
            await self._ensure_loaded_locked()
            data = await self._db.get(url)
            if data is None:
                return None

            if data.get("exp", 0) <= time.time():
                self.logger.debug(f"缓存过期: key={url}")
                if await self._db.remove(url):
                    self._dirty = True
                return None
            self.logger.debug(f"缓存命中: key={url}")
            return _StorageWrapper.model_validate(data).entry

    async def set(self, url: str, entry: CacheEntry) -> None:
        if not self.enabled:
            return
        sw = _StorageWrapper(entry=entry, exp=int(time.time() + self._ttl))
        async with self._lock:
            await self._ensure_loaded_locked()
            await self._db.remove(url)
            await self._db.set(url, sw.model_dump())
            removed = await self._evict_overflow_locked()
            self._dirty = True
            self.logger.debug(f"缓存写入: key={url}, evicted={removed}")

    async def remove(self, url: str) -> None:
        if not self.enabled:
            return
        async with self._lock:
            await self._ensure_loaded_locked()
            if await self._db.remove(url):
                self._dirty = True

    def start_cleanup(self):
        """启动后台清理任务"""
        if not self.enabled:
            self.logger.debug("持久缓存已禁用, 跳过后台任务")
            return
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
            self.logger.debug(
                f"后台缓存任务已启动, save_interval={self._save_interval}s, cleanup_interval={self._cleanup_interval}s"
            )

    async def close(self) -> None:
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
        if not self.enabled:
            return
        async with self._lock:
            await self._save_locked()

    async def _periodic_cleanup(self):
        while True:
            await asyncio.sleep(self._save_interval)
            if not self._loaded:
                continue
            async with self._lock:
                now = time.monotonic()
                if now - self._last_cleanup_at >= self._cleanup_interval:
                    expired = await self._remove_expired_locked()
                    overflow = await self._evict_overflow_locked()
                    if expired or overflow:
                        self._dirty = True
                        self.logger.debug(f"定时清理缓存: expired={expired}, overflow={overflow}")
                    self._last_cleanup_at = now
                await self._save_locked()

    async def _remove_expired_locked(self) -> int:
        now = time.time()
        removed = 0
        all_keys = await self._db.all()
        for key in all_keys:
            data = await self._db.get(key)
            if data and data.get("exp", 0) <= now:
                await self._db.remove(key)
                removed += 1
        return removed

    async def _evict_overflow_locked(self) -> int:
        if self._max_entries <= 0:
            return 0
        keys = await self._db.all()
        overflow = len(keys) - self._max_entries
        if overflow <= 0:
            return 0
        for key in keys[:overflow]:
            await self._db.remove(key)
        return overflow


parse_cache = TTLCache(ttl=60 * 60, maxsize=1000)  # 解析结果缓存 1 小时
persistent_cache = PersistentCache(
    bs.cache_path / "cache.json",
    ttl=bs.cache_time * 60,
    save_interval=bs.cache_save_interval * 60,
    cleanup_interval=bs.cache_cleanup_interval * 60,
    max_entries=bs.cache_max_entries,
)
