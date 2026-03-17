from parsehub import ParseHub
from parsehub.types import (
    AnyParseResult,
)

from core import platforms_config
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
        pid = self.parser.get_platform(url)
        if pc := platforms_config.get(pid.id):
            logger.debug(f"使用平台配置: {pc}")
            pr = await self.parser.parse(url, cookie=pc.roll_cookie(), proxy=pc.roll_parser_proxy())
        else:
            pr = await self.parser.parse(url)
        logger.debug(f"解析完成: {pr}")
        return pr

    async def get_raw_url(self, url: str, clean_all: bool = True) -> str:
        pid = self.parser.get_platform(url)
        if pc := platforms_config.get(pid.id):
            logger.debug(f"使用平台配置: {pc}")
            raw_url = await self.parser.get_raw_url(url, proxy=pc.roll_parser_proxy(), clean_all=clean_all)
        else:
            raw_url = await self.parser.get_raw_url(url, clean_all=clean_all)
        logger.debug(f"原始 URL: {raw_url}")
        return raw_url
