from ..base.yt_dlp_parser import YtParse, YtVideoParseResult


class FacebookParse(YtParse):
    __match__ = r"^(http(s)?://)?.+facebook.com/(watch\?v|share/v).*"

    async def parse(
        self, url: str, progress=None, progress_args=()
    ) -> "YtVideoParseResult":
        url = await self.get_raw_url(url)
        return await super().parse(url, progress, progress_args)
