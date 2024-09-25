from dataclasses import dataclass
from typing import Callable, Union

import httpx

from ..base.base import Parse
from ...config.config import ph_cfg
from ...types import VideoParseResult, ImageParseResult, ParseError, Video, Image


class DouyinParse(Parse):
    __match__ = r"^(http(s)?://)?.+douyin.com/.+|^(http(s)?://)?.+tiktok.com/.+"
    __redirect_keywords__ = ["v.douyin", "vt.tiktok"]

    async def parse(
        self, url: str, progress: Callable = None, progress_args=()
    ) -> Union["VideoParseResult", "ImageParseResult", None]:
        url = await self.get_raw_url(url)
        data = await self.parse_api(url)

        match data.type:
            case "video":
                return await self.video_parse(url, data)
            case "image":
                return await self.image_parse(url, data)
            case _:
                raise ValueError(f"未知类型: {data.type}")

    @staticmethod
    async def parse_api(url) -> "DYResult":
        if not ph_cfg.douyin_api:
            raise ParseError("抖音解析API未配置")

        async with httpx.AsyncClient(timeout=10) as client:
            params = {"url": url, "minimal": False}
            response = await client.get(
                f"{ph_cfg.douyin_api}/api/hybrid/video_data", params=params
            )
        if response.status_code != 200:
            raise ParseError("抖音解析失败")
        return DYResult.parse(url, response.json())

    @staticmethod
    async def video_parse(url, result: "DYResult"):
        return VideoParseResult(
            raw_url=url,
            title=result.desc,
            video=Video(result.video, thumb_url=result.thumb),
        )

    @staticmethod
    async def image_parse(url, result: "DYResult"):
        return ImageParseResult(
            raw_url=url,
            title=result.desc,
            photo=[Image(i, thumb_url=result.thumb) for i in result.image_list],
        )


@dataclass
class DYResult:
    type: str
    platform: str
    video: str
    desc: str = ""
    image_list: list[str] = None
    thumb: str = None

    @staticmethod
    def parse(url: str, json_dict: dict):
        platform = "douyin" if "douyin" in url else "tiktok"

        data = json_dict.get("data")
        desc = data.get("desc")

        if images := data.get("images"):
            type_ = "image"
            video = None
            thumb = None

            image_list = [image["url_list"][-1] for image in images]
        else:
            type_ = "video"
            image_list = None
            video_d = data.get("video")

            if platform == "douyin":
                video = video_d["bit_rate"]
                if not video:
                    raise ParseError("抖音解析失败: 未获取到视频下载地址")
                video.sort(key=lambda x: x["quality_type"])
                video = video[0]["play_addr"]["url_list"][-1]
                thumb = video_d["cover"]["url_list"][-1]
            else:
                video = video_d["bitrateInfo"]
                if not video:
                    raise ParseError("抖音解析失败: 未获取到视频下载地址")
                video = video[0]["PlayAddr"]["UrlList"][-1]
                thumb = video_d["cover"]

        return DYResult(
            type=type_,
            video=video,
            desc=desc,
            image_list=image_list,
            platform=platform,
            thumb=thumb,
        )
