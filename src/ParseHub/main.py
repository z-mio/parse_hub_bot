from typing import Type
from .parsers.base.base import Parse
from .types.parse_result import ParseResult
from .utiles.utile import get_all_subclasses, match_url


class ParseHub:
    def __init__(self):
        self.parsers: list[Type[Parse]] = self._load_parser()

    def select_parser(self, url: str) -> Type[Parse] | None:
        """选择解析器"""
        for parser in self.parsers:
            if parser().match(match_url(url)):
                return parser

    @staticmethod
    def _load_parser() -> list[Type[Parse]]:
        all_subclasses = get_all_subclasses(Parse)
        return [
            subclass for subclass in all_subclasses if getattr(subclass, "__match__")
        ]

    async def parse(self, url: str) -> "ParseResult":
        """会自动从字符串中提取链接"""
        if parser := self.select_parser(url):
            return await parser().parse(url)
        raise ValueError("不支持的平台")
