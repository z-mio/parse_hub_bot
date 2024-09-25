from typing import Union

from ..base.yt_dlp_parser import YtParse, YtVideoParseResult, YtImageParseResult


class YtbParse(YtParse):
    __match__ = r"^(http(s)?://).*youtu(be|.be)?(\.com)?/(?!live)(?!@).+"
    __reserved_parameters__ = ["v", "list", "index"]

    async def parse(
        self, url: str, progress=None, progress_args=()
    ) -> Union["YtVideoParseResult", "YtImageParseResult"]:
        url = await self.get_raw_url(url)
        self.params["writesubtitles"] = True
        return await super().parse(url, progress, progress_args)
