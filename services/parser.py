from parsehub import ParseHub
from parsehub.types import (
    AnyParseResult,
)

from core import pl_cfg
from log import logger

logger = logger.bind(name="ParseService")


class ParseService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self.parser = ParseHub()

    async def parse(self, url: str) -> AnyParseResult:
        logger.debug(f"开始解析 {url}")
        p = self.parser.get_platform(url)
        if pc := pl_cfg.get(p.id):
            logger.debug(f"使用平台配置: {pc}")
            pr = await self.parser.parse(url, cookie=pl_cfg.roll_cookie(p.id), proxy=pl_cfg.roll_parser_proxy(p.id))
        else:
            pr = await self.parser.parse(url)
        logger.debug(f"解析完成: {pr}")
        return pr

    async def get_raw_url(self, url: str, clean_all: bool = True) -> str:
        p = self.parser.get_platform(url)
        if pc := pl_cfg.get(p.id):
            logger.debug(f"使用平台配置: {pc}")
            raw_url = await self.parser.get_raw_url(url, proxy=pl_cfg.roll_parser_proxy(p.id), clean_all=clean_all)
        else:
            raw_url = await self.parser.get_raw_url(url, clean_all=clean_all)
        logger.debug(f"原始 URL: {raw_url}")
        return raw_url
