from typing import Self

from parsehub import ParseHub, Platform
from parsehub.types import (
    AnyParseResult,
)

from core import pl_cfg
from log import logger

from .cookie_health import cookie_health

logger = logger.bind(name="ParseService")


class ParseService:
    _instance: Self | None = None

    def __new__(cls) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        self.parser = ParseHub()

    def get_platform(self, url: str) -> Platform:
        p = self.parser.get_platform(url)
        if not p:
            raise ValueError("不支持的平台")
        return p

    async def parse(self, url: str) -> AnyParseResult:
        logger.debug(f"开始解析 {url}")
        p = self.get_platform(url)

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            cookie = pl_cfg.roll_cookie(p.id)
            cookie_value = cookie.get_secret_value() if cookie else None
            try:
                proxy = pl_cfg.roll_parser_proxy(p.id)
                logger.debug(f"使用配置: proxy={proxy}, cookie={cookie}, attempt={attempt}/{max_retries}")
                pr = await self.parser.parse(url, cookie=cookie_value, proxy=proxy)
                logger.debug(f"解析完成: {pr}")
                if cookie_value:
                    cookie_health.record_success(cookie_value)
                return pr
            except Exception as e:
                logger.warning(f"解析失败, attempt={attempt}/{max_retries}, err={e}")
                if cookie_value:
                    cookie_health.record_failure(p.id, cookie_value, e, url)
                if attempt >= max_retries:
                    raise Exception(e) from e
        raise

    async def test_cookie(self, url: str, cookie: str) -> None:
        """用指定 cookie 解析一次, 结果计入该 cookie 的统计"""
        p = self.get_platform(url)
        try:
            await self.parser.parse(url, cookie=cookie, proxy=pl_cfg.roll_parser_proxy(p.id))
        except Exception as e:
            cookie_health.record_failure(p.id, cookie, e, url, alert=False)
            raise
        cookie_health.record_success(cookie)

    async def get_raw_url(self, url: str, clean_all: bool = True) -> str:
        p = self.get_platform(url)

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                proxy = pl_cfg.roll_parser_proxy(p.id)
                logger.debug(f"使用配置: proxy={proxy}, attempt={attempt}/{max_retries}")
                raw_url = await self.parser.get_raw_url(url, proxy=proxy, clean_all=clean_all)
                logger.debug(f"原始 URL: {raw_url}")
                return str(raw_url)
            except Exception as e:
                logger.warning(f"获取原始 URL 失败, attempt={attempt}/{max_retries}, err={e}")
                if attempt >= max_retries:
                    raise Exception(e) from e
        raise
