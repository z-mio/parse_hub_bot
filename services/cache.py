import asyncio
import time
from typing import Any

from log import logger

logger = logger.bind(name="Cache")


class TTLCache:
    def __init__(self, ttl: float = 300):
        self._ttl = ttl
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                logger.debug(f"缓存未命中: key={key}")
                return None
            value, expire_at = entry
            if time.monotonic() > expire_at:
                logger.debug(f"缓存已过期: key={key}")
                del self._store[key]
                return None
            logger.debug(f"缓存命中: key={key}")
            return value

    async def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        async with self._lock:
            effective_ttl = ttl or self._ttl
            logger.debug(f"缓存写入: key={key}, ttl={effective_ttl}s")
            self._store[key] = (value, time.monotonic() + effective_ttl)

    async def pop(self, key: str) -> Any | None:
        async with self._lock:
            entry = self._store.pop(key, None)
            if entry is None:
                logger.debug(f"缓存 pop 未命中: key={key}")
                return None
            value, expire_at = entry
            if time.monotonic() > expire_at:
                logger.debug(f"缓存 pop 已过期: key={key}")
                return None
            logger.debug(f"缓存 pop 命中: key={key}")
            return value
