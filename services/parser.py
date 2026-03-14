from parsehub import ParseHub
from parsehub.types import (
    AnyParseResult,
)

from core.platform_config import platforms_config
from log import logger

logger = logger.bind(name="ParseService")

_parse_hub = ParseHub()


class ParseService:
    def __init__(self, url: str):
        self.url = url
        self.parser = _parse_hub

    async def parse(self) -> AnyParseResult:
        logger.debug(f"开始解析 {self.url}")
        pid = self.parser.get_platform(self.url)
        if pc := platforms_config.get(pid):
            logger.debug(f"使用平台配置: {pc}")
            pr = await self.parser.parse(self.url, cookie=pc.roll_cookie, proxy=pc.roll_parser_proxy)
        else:
            pr = await self.parser.parse(self.url)
        logger.debug(f"解析完成: {pr}")
        return pr
