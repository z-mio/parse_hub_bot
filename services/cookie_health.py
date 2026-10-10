import asyncio
import hashlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from log import logger

logger = logger.bind(name="CookieHealth")

ALERT_FAIL_STREAK = 3
"""连续失败达到该次数时通知管理员"""


@dataclass
class CookieStat:
    fail_streak: int = 0
    last_success_at: float | None = None
    last_failure_at: float | None = None
    last_error: str | None = None
    alerted: bool = False


@dataclass(frozen=True)
class CookieAlert:
    platform_id: str
    cookie: str
    stat: CookieStat
    url: str


type CookieAlertNotifier = Callable[[CookieAlert], Awaitable[None]]


class CookieHealth:
    """cookie 使用情况统计, 只存内存, 重启后清零。带 cookie 的解析失败都算该 cookie 失败一次"""

    def __init__(self) -> None:
        self._stats: dict[str, CookieStat] = {}
        self._last_failed_url: dict[str, str] = {}
        self._notifier: CookieAlertNotifier | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self._testing: set[str] = set()

    @staticmethod
    def _key(cookie: str) -> str:
        return hashlib.sha256(cookie.encode()).hexdigest()

    def set_notifier(self, notifier: CookieAlertNotifier) -> None:
        self._notifier = notifier

    def get(self, cookie: str) -> CookieStat | None:
        return self._stats.get(self._key(cookie))

    def set_testing(self, cookies: list[str], testing: bool) -> None:
        keys = {self._key(c) for c in cookies}
        if testing:
            self._testing |= keys
        else:
            self._testing -= keys

    def is_testing(self, cookie: str) -> bool:
        return self._key(cookie) in self._testing

    def last_failed_url(self, platform_id: str) -> str | None:
        return self._last_failed_url.get(platform_id)

    def record_success(self, cookie: str) -> None:
        stat = self._stats.setdefault(self._key(cookie), CookieStat())
        stat.fail_streak = 0
        stat.alerted = False
        stat.last_success_at = time.time()

    def record_failure(self, platform_id: str, cookie: str, error: Exception, url: str, *, alert: bool = True) -> None:
        stat = self._stats.setdefault(self._key(cookie), CookieStat())
        stat.fail_streak += 1
        stat.last_failure_at = time.time()
        stat.last_error = str(error) or type(error).__name__
        self._last_failed_url[platform_id] = url

        if not alert or stat.fail_streak < ALERT_FAIL_STREAK or stat.alerted or not self._notifier:
            return
        stat.alerted = True
        task = asyncio.ensure_future(self._notifier(CookieAlert(platform_id, cookie, stat, url)))
        self._tasks.add(task)
        task.add_done_callback(self._on_done)

    def _on_done(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and (exc := task.exception()) is not None:
            logger.opt(exception=exc).error("cookie 失效通知发送失败")

    def prune(self, cookies: set[str]) -> None:
        """丢弃已不在配置中的 cookie 的统计"""
        keep = {self._key(c) for c in cookies}
        for key in self._stats.keys() - keep:
            del self._stats[key]


cookie_health = CookieHealth()
