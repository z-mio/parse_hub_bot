import re
from abc import ABC, abstractmethod
from typing import Callable
from urllib.parse import urlparse, parse_qs

import httpx

from ...config.config import UA
from ...types import ParseResult


class Parse(ABC):
    __match__: str = None
    """链接匹配规则"""
    __reserved_parameters__ = []
    """要保留的参数, 例如翻页. 默认清除全部参数"""
    __redirect_keywords__ = []
    """如果链接包含其中之一, 则遵循重定向规则"""

    def match(self, url: str) -> bool:
        """判断是否匹配该解析器"""
        return bool(re.match(self.__match__, url))

    @abstractmethod
    async def parse(self, url: str) -> "ParseResult":
        """解析"""
        raise NotImplementedError

    @staticmethod
    def _status(progress: Callable = None, progress_args=()):
        """用于返回解析状态"""

        async def fn(code: int, text: str = None):
            if progress:
                return await progress(code, text, *progress_args)

        return fn

    async def get_raw_url(self, url: str) -> str:
        """
        清除链接中的参数
        :param url: 链接
        :return:
        """

        if any(map(lambda x: x in url, self.__redirect_keywords__)):
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    url, follow_redirects=True, headers={"User-Agent": UA}
                )
                r.raise_for_status()
                url = str(r.url)

        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)

        for i in query_params.copy().keys():
            if i not in self.__reserved_parameters__:
                del query_params[i]
        new_query = "&".join([f"{k}={v[0]}" for k, v in query_params.items()])
        return parsed_url._replace(query=new_query).geturl()
