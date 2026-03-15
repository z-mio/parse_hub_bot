import asyncio
import time
from typing import Any


class TTLCache:
    def __init__(self, ttl: float = 300):
        self._ttl = ttl
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expire_at = entry
            if time.monotonic() > expire_at:
                del self._store[key]
                return None
            return value

    async def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        async with self._lock:
            self._store[key] = (value, time.monotonic() + (ttl or self._ttl))

    async def pop(self, key: str) -> Any | None:
        async with self._lock:
            entry = self._store.pop(key, None)
            if entry is None:
                return None
            value, expire_at = entry
            return value if time.monotonic() <= expire_at else None
