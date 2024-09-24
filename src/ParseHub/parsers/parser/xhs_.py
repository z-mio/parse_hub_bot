import re
from typing import Union

import httpx
from xhs import DataFetchError, XhsClient, help
from xhs.exception import NeedVerifyError

from ..base.base import Parse
from ...config.config import ph_cfg
from ...types import VideoParseResult, ImageParseResult, ParseError


class XhsParse(Parse):
    __match__ = r"^(http(s)?://)?.+(xiaohongshu|xhslink).com/.+"
    __redirect_keywords__ = ["xhslink"]

    async def parse(
        self, url: str, progress=None, progress_args=()
    ) -> Union["VideoParseResult", "ImageParseResult"]:
        if not ph_cfg.douyin_api:
            raise ParseError("小红书解析API未配置")

        for _ in range(10):
            xhs_client = XhsClient(self._cookie, sign=self.sign)
            try:
                url = await self.get_raw_url(url)
                xhs_id = self.get_id_by_url(url)
                note = xhs_client.get_note_by_id(xhs_id)

                if note["type"] == "video":
                    return await self.video_parse(url, note)
                elif note["type"] == "normal":
                    return await self.image_parse(url, note)
            except DataFetchError:
                ...
            except NeedVerifyError:
                ...
        raise ParseError("获取失败")

    @staticmethod
    async def video_parse(url, result: dict):
        video_url = help.get_video_url_from_note(result)
        return VideoParseResult(
            title=result["title"],
            desc=result["desc"],
            video=video_url,
            raw_url=url,
        )

    @staticmethod
    async def image_parse(url, result: dict):
        image_list = help.get_imgs_url_from_note(result)
        return ImageParseResult(
            title=result["title"],
            photo=image_list,
            desc=result["desc"],
            raw_url=url,
        )

    @staticmethod
    def sign(uri, data=None, a1="", web_session=""):
        res = httpx.post(
            f"{ph_cfg.xhs_api}/sign",
            json={"uri": uri, "data": data, "a1": a1, "web_session": web_session},
        )
        signs = res.json()
        return {"x-s": signs["x-s"], "x-t": signs["x-t"]}

    @staticmethod
    def get_id_by_url(url: str):
        xhsid = re.search(r"[0-9a-fA-F]{24}", url)
        if xhsid:
            return xhsid.group(0)
        else:
            raise ParseError(f"获取小红书原链接失败")

    @property
    def _cookie(self):
        return ph_cfg.xhs_cookie
