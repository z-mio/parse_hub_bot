import asyncio
from ...utiles.img_host import ImgHost
import time
from dataclasses import dataclass
from typing import Union, Callable

from yt_dlp import YoutubeDL

from .base import Parse
from ...config.config import ph_cfg
from ...types import (
    VideoParseResult,
    ImageParseResult,
    Video,
    Subtitles,
    DownloadResult,
)


class YtParse(Parse):
    """yt-dlp解析器"""

    params = {
        "format": "(mp4+bestaudio) / (bestvideo* + bestaudio / best)",
        "quiet": True,  # 不输出日志
        "writethumbnail": True,  # 下载缩略图
        "writesubtitles": False,  # 下载字幕
        "writeautomaticsub": True,  # 下载自动翻译的字幕
        "subtitlesformat": "ttml",  # 字幕格式
        "subtitleslangs": ["en", "zh-CN"],  # 字幕语言
        "postprocessors": [
            {
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4",  # 视频格式
            }
        ],
        "playlist_items": "1",  # 分p列表默认解析第一个
        # "progress_hooks": [self.hook], # 进度回调
    }

    async def parse(
        self, url: str, progress=None, progress_args=()
    ) -> Union["YtVideoParseResult", "YtImageParseResult"]:
        url = await self.get_raw_url(url)
        video_info = await self._parse(url)
        _d = {
            "title": video_info.title,
            "desc": video_info.description,
            "raw_url": url,
            "dl": video_info,
        }
        if video_info.duration > 5400:
            return YtImageParseResult(photo=[video_info.thumbnail], **_d)
        else:
            return YtVideoParseResult(video=video_info.url, **_d)

    async def _parse(self, url, params=None) -> "YtVideoInfo":
        with YoutubeDL(params or self.params) as ydl:
            dl = ydl.extract_info(url, download=False)
        if dl.get("_type"):
            dl = dl["entries"][0]
            url = dl["webpage_url"]
        title = dl["title"]
        duration = dl["duration"]
        thumbnail = dl["thumbnail"]
        description = dl["description"]

        return YtVideoInfo(
            raw_video_info=dl,
            title=title,
            description=description,
            thumbnail=thumbnail,
            duration=duration,
            url=url,
        )

    # def hook(self, d):
    #     current = d.get("downloaded_bytes", 0)
    #     total = d.get("total_bytes", 0)
    #     if round(current * 100 / total, 1) % 25 == 0:
    #         self.loop.create_task(
    #             self.set_status(0, f"下 载 中...|{current * 100 / total:.0f}%")
    #         )


class YtVideoParseResult(VideoParseResult):
    def __init__(
        self,
        title=None,
        video=None,
        desc=None,
        raw_url=None,
        dl: "YtVideoInfo" = None,
    ):
        """dl: yt-dlp解析结果"""
        self.dl = dl
        super().__init__(title=title, video=video, desc=desc, raw_url=raw_url)

    async def download(
        self,
        callback: Callable = None,
        callback_args: tuple = (),
        proxies: dict | str = None,
    ) -> DownloadResult:
        """下载视频"""
        if not self.media.is_url:
            return self.media

        # 创建保存目录
        dir_ = ph_cfg.DOWNLOAD_DIR.joinpath(f"{time.time_ns()}")
        dir_.mkdir(parents=True, exist_ok=True)

        # 输出模板
        yto = YtParse().params
        yto["outtmpl"] = f"{dir_.joinpath('ytdlp_%(id)s')}.%(ext)s"

        text = "下载合并中...请耐心等待..."
        if self.dl.duration > 1800:
            # 视频超过30分钟，获取最低画质
            text += "\n视频超过30分钟，获取最低画质"
            yto["format"] = "worstvideo* + worstaudio / worst"

        if callback:
            await callback(0, 0, text, *callback_args)

        with YoutubeDL(yto) as ydl:
            await asyncio.to_thread(ydl.download, [self.media.path])

        video_path = (v := list(dir_.glob("*.mp4"))) and v[0]
        subtitles = (v := list(dir_.glob("*.ttml"))) and Subtitles().parse(v[0])
        thumb = (
            v := list(dir_.glob("*.webp")) or list(dir_.glob("*.jpg"))
        ) and await ImgHost().ipfs(v[0])
        return DownloadResult(
            self, Video(path=str(video_path), subtitles=subtitles, thumb_url=thumb)
        )


class YtImageParseResult(ImageParseResult):
    def __init__(
        self, title="", photo=None, desc=None, raw_url=None, dl: "YtVideoInfo" = None
    ):
        """dl: yt-dlp解析结果"""
        self.dl = dl
        super().__init__(title=title, photo=photo, desc=desc, raw_url=raw_url)


@dataclass
class YtVideoInfo:
    """raw_video_info: yt-dlp解析结果"""

    raw_video_info: dict
    title: str
    description: str
    thumbnail: str
    duration: int
    url: str
