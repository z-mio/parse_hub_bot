import asyncio
import hashlib
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from pickledb import PickleDB

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


def encrypt(text: str):
    """hash加密"""
    md5 = hashlib.md5()
    md5.update(text.encode("utf-8"))
    return md5.hexdigest()[:16]


@dataclass
class CacheEntry:
    """file_id 缓存条目"""

    file_ids: list[str | list[str]]
    """与 media 同索引, 嵌套 list 表示切割图; 单项可为 file_id 字符串"""
    title: str = ""
    caption: str = ""
    telegraph_url: str | None = None
    media_types: list[str] = field(default_factory=list)
    """与 file_ids 同索引, 记录每个媒体的类型: photo / video / animation / document"""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CacheEntry":
        return cls(**data)


class FileIdCache:
    def __init__(self, db_path: str):
        self._db = PickleDB(db_path)
        self.logger = logger.bind(name="FileIdCache")
        self.logger.debug(f"file_id 持久化缓存已加载: {db_path}")

    async def get(self, url: str) -> CacheEntry | None:
        key = encrypt(url)
        async with self._db as db:
            data = await db.get(key)
        if data is None:
            return None
        self.logger.debug(f"file_id 缓存命中: key={key} value={data}")
        return CacheEntry.from_dict(data)

    async def set(self, url: str, entry: CacheEntry) -> None:
        key = encrypt(url)
        async with self._db as db:
            await db.set(key, entry.to_dict())
            self.logger.debug(f"file_id 缓存写入: key={key} value={entry}")

    async def remove(self, url: str) -> None:
        key = encrypt(url)
        async with self._db as db:
            await db.remove(key)


parse_cache = TTLCache(ttl=300)
file_id_cache = FileIdCache(bs.data_path / "file_id_cache.json")
