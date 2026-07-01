import asyncio
import functools
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from core import bs


class ParseRateLimitExceeded(Exception):
    """解析速率限制异常。"""

    def __init__(self, retry_after: float, *, should_notify: bool = False) -> None:
        self.retry_after = max(0.0, retry_after)
        self.should_notify = should_notify
        super().__init__(f"解析过于频繁, 请在 {self.retry_after:.1f}s 后重试")


@dataclass
class _UserParseRateLimitState:
    trigger_records: deque[float] = field(default_factory=deque)
    limited_records: deque[float] = field(default_factory=deque)
    limited_until: float = 0.0
    limited_notify_until: float = 0.0


class ParseRateLimiter:
    """解析速率限制器。"""

    def __init__(self) -> None:
        self._states: dict[int | str, _UserParseRateLimitState] = {}
        self._lock = asyncio.Lock()

    async def check(self, user_id: int | str) -> None:
        if not bs.rate_limit_enabled or bs.rate_limit_burst <= 0:
            return

        async with self._lock:
            now = time.monotonic()
            self._cleanup(now)
            state = self._states.setdefault(user_id, _UserParseRateLimitState())

            if state.limited_until > now:
                self._check_limited_state(state, now)
                return

            if state.limited_until:
                self._reset(state)

            self._check_trigger_state(state, now)

    def decorator[T](
        self,
        get_user_id: Callable[..., int | str | None],
    ) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
        """按用户维度限制解析频率。"""

        def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
            @functools.wraps(func)
            async def wrapper(*args: Any, **kwargs: Any) -> T:
                user_id = get_user_id(*args, **kwargs)
                if user_id is not None:
                    await self.check(user_id)
                return await func(*args, **kwargs)

            return wrapper

        return decorator

    def _check_limited_state(self, state: _UserParseRateLimitState, now: float) -> None:
        duration_retry_after = state.limited_until - now
        if bs.rate_limit_throttle <= 0:
            notify_until = min(now + bs.rate_limit_throttle_window, state.limited_until)
            raise self._limited_exceeded(state, duration_retry_after, notify_until, now)

        self._trim(state.limited_records, now, bs.rate_limit_throttle_window)
        if len(state.limited_records) >= bs.rate_limit_throttle:
            window_reset_at = state.limited_records[0] + bs.rate_limit_throttle_window
            window_retry_after = window_reset_at - now
            notify_until = min(window_reset_at, state.limited_until)
            raise self._limited_exceeded(state, min(window_retry_after, duration_retry_after), notify_until, now)
        state.limited_records.append(now)

    def _check_trigger_state(self, state: _UserParseRateLimitState, now: float) -> None:
        self._trim(state.trigger_records, now, bs.rate_limit_burst_window)
        state.trigger_records.append(now)
        if len(state.trigger_records) >= bs.rate_limit_burst:
            self._reset(state)
            state.limited_until = now + bs.rate_limit_cooldown
            state.limited_records.append(now)

    def _cleanup(self, now: float) -> None:
        trigger_window = bs.rate_limit_burst_window
        limited_window = bs.rate_limit_throttle_window
        expired_keys = [
            key
            for key, state in self._states.items()
            if state.limited_until <= now
            and (not state.trigger_records or state.trigger_records[-1] <= now - trigger_window)
            and (not state.limited_records or state.limited_records[-1] <= now - limited_window)
        ]
        for key in expired_keys:
            self._states.pop(key, None)

    @staticmethod
    def _limited_exceeded(
        state: _UserParseRateLimitState,
        retry_after: float,
        notify_until: float,
        now: float,
    ) -> ParseRateLimitExceeded:
        should_notify = now >= state.limited_notify_until
        if should_notify:
            state.limited_notify_until = notify_until
        return ParseRateLimitExceeded(retry_after, should_notify=should_notify)

    @staticmethod
    def _reset(state: _UserParseRateLimitState) -> None:
        state.trigger_records.clear()
        state.limited_records.clear()
        state.limited_until = 0.0
        state.limited_notify_until = 0.0

    @staticmethod
    def _trim(records: deque[float], now: float, window: float) -> None:
        expire_before = now - window
        while records and records[0] <= expire_before:
            records.popleft()


parse_rate_limiter = ParseRateLimiter()
parse_rate_limit = parse_rate_limiter.decorator

__all__ = ["parse_rate_limit", "ParseRateLimitExceeded"]
