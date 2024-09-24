import re

from ..base.base import Parse
from ...types import (
    MultimediaParseResult,
    Video,
    Image,
    Ani,
    VideoParseResult,
    ImageParseResult,
)
from ...utiles.weibo_api import WeiboAPI, MediaType


class WeiboParse(Parse):
    __match__ = r"^(http(s)?://)(m\.|)weibo.(com|cn)/.*"

    async def parse(
        self, url: str, progress=None, progress_args=()
    ) -> MultimediaParseResult | VideoParseResult | ImageParseResult:
        url = await self.get_raw_url(url)

        weibo = await WeiboAPI().parse(url)
        data = weibo.data
        text = self.f_text(data.content)
        media = []
        if not data.pic_infos and data.page_info:
            if data.page_info.object_type == MediaType.VIDEO:
                return VideoParseResult(
                    desc=text,
                    raw_url=url,
                    video=Video(
                        data.page_info.media_info.mp4_hd_url,
                        thumb_url=data.page_info.page_pic,
                    ),
                )
        for i in (
            ((rs := data.retweeted_status) and rs.pic_infos)
            or data.pic_infos
            or (data.mix_media_info and data.mix_media_info.items)
        ):
            match i.type:
                case MediaType.VIDEO:
                    media.append(Video(i.media_url, thumb_url=i.thumb_url))
                case MediaType.LIVE_PHOTO:
                    media.append(Video(i.media_url, ext="mov", thumb_url=i.thumb_url))
                case MediaType.GIF:
                    media.append(Ani(i.media_url, thumb_url=i.thumb_url))
                case _:
                    media.append(Image(i.media_url))
        if all(isinstance(m, Image) for m in media):
            return ImageParseResult(desc=text, raw_url=url, photo=media)
        return MultimediaParseResult(desc=text, raw_url=url, media=media)

    @staticmethod
    def f_text(text: str) -> str:
        # text = re.sub(r'<a  href="https://video.weibo.com.*?>.*的微博视频.*</a>', "", text)
        # text = re.sub(r"<[^>]+>", " ", text)
        return text.strip()
