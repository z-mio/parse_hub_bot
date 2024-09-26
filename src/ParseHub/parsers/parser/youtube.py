from typing import Union

from ..base.yt_dlp_parser import YtParse, YtVideoParseResult, YtImageParseResult


class YtbParse(YtParse):
    __match__ = r"^(http(s)?://).*youtu(be|.be)?(\.com)?/(?!live)(?!@).+"
    __reserved_parameters__ = ["v", "list", "index"]

    async def parse(
        self, url: str, progress=None, progress_args=()
    ) -> Union["YtVideoParseResult", "YtImageParseResult"]:
        url = await self.get_raw_url(url)

        return await super().parse(url, progress, progress_args)

    @property
    def params(self):
        sub = {
            "writesubtitles": True,  # 下载字幕
            "writeautomaticsub": True,  # 下载自动翻译的字幕
            "subtitlesformat": "ttml",  # 字幕格式
            # "subtitleslangs": ["en", "ja", "zh-CN"],  # 字幕语言
        }
        return sub | super().params
