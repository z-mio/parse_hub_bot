import os
import time
from typing import Callable, Generic, TypeVar
from .media import Media, Video
from ..utiles.utile import progress, img2base64
from ..utiles.download_file import download_file
import asyncio
from abc import ABC
from langchain_core.messages import HumanMessage, SystemMessage
from ..tools import LLM, Transcriptions
from .media import Image, MediaT
from .subtitles import Subtitles, Subtitle
from .summary_result import SummaryResult
from ..config.config import ph_cfg

CN_PROMPT = """
你是一个有用的助手，总结文章和视频字幕的要点。
用“简体中文”总结3到8个要点，并在最后总结全部。
"""
PROMPT = """
You are a useful assistant to summarize the main points of articles and video captions.
Summarize 3 to 8 points in "Simplified Chinese" and summarize them all at the end.
""".strip()

T = TypeVar("T", bound="ParseResult")


class ParseResult(ABC):
    """解析结果基类"""

    def __init__(
        self,
        title: str,
        media: list[MediaT] | MediaT,
        desc: str = "",
        raw_url: str = None,
    ):
        """
        :param title: 标题
        :param media: 媒体下载链接
        :param desc: 正文
        :param raw_url: 原始帖子链接
        """
        self.title = (title or "").strip()
        self.media = media
        self.desc = (desc or "").strip()
        self.raw_url = raw_url

    async def download(
        self,
        callback: Callable = None,
        callback_args: tuple = (),
        proxies: dict | str = None,
    ) -> "DownloadResult":
        """
        :param callback: 下载进度回调函数
        :param callback_args: 下载进度回调函数参数
        :param proxies: 代理设置
        :return: 本地视频路径

        .. note::
        下载进度回调函数签名: async def callback(current: int, total: int, status: str|None, *args) -> None:
        status: 进度或其他状态信息
        """
        if isinstance(self.media, list):
            path_list = []
            op = ph_cfg.DOWNLOAD_DIR / f"{time.time_ns()}"
            for i, image in enumerate(self.media):
                if not image.is_url:
                    path_list.append(image)
                    continue

                f = await download_file(
                    image.path, f"{op}/{i}.{image.ext}", proxies=proxies
                )

                path_list.append(image.__class__(f, ext=image.ext))

                if callback:
                    await callback(
                        len(path_list),
                        len(self.media),
                        progress(len(path_list), len(self.media), "数量"),
                        *callback_args,
                    )
            return DownloadResult(self, path_list)
        else:
            if not self.media.is_url:
                return self.media

            async def _callback(current, total, *args):
                await callback(
                    current,
                    total,
                    progress(current, total, "百分比"),
                    *args,
                )

            r = await download_file(
                self.media.path,
                f"{time.time_ns()}.{self.media.ext}",
                proxies=proxies,
                progress=_callback if callback else None,
                progress_args=callback_args,
            )

            # 小于10KB为下载失败
            if not os.stat(r).st_size > 10 * 1024:
                os.remove(r)
                raise Exception("下载失败")
            return DownloadResult(self, self.media.__class__(r, ext=self.media.ext))


class VideoParseResult(ParseResult):
    def __init__(
        self,
        title: str = "",
        video: str | Video = None,
        raw_url: str = None,
        desc: str = "",
    ):
        video = Video(video) if isinstance(video, str) else video
        super().__init__(
            title=title,
            media=video,
            desc=desc,
            raw_url=raw_url,
        )


class ImageParseResult(ParseResult):
    def __init__(
        self,
        title: str = "",
        photo: list[str | Image] = None,
        desc: str = "",
        raw_url: str = None,
    ):
        photo = [Image(p) if isinstance(p, str) else p for p in photo]
        super().__init__(title=title, media=photo, desc=desc, raw_url=raw_url)


class MultimediaParseResult(ParseResult):
    def __init__(
        self,
        title: str = "",
        media: list[Media] = None,
        desc: str = "",
        raw_url: str = None,
    ):
        super().__init__(title=title, media=media, desc=desc, raw_url=raw_url)


class DownloadResult(Generic[T]):
    """下载结果"""

    def __init__(self, parse_result: T, media: list[MediaT] | MediaT):
        self.pr = parse_result
        self.media = media

    def exists(self) -> bool:
        """是否存在本地文件"""
        if isinstance(self.media, list):
            return all(m.exists() for m in self.media)
        else:
            return self.media.exists()

    async def summary(self) -> "SummaryResult":
        """总结解析结果"""
        if not isinstance(self.media, list):
            media = [self.media]
        else:
            media = self.media

        subtitles = ""
        tasks = []
        for i in media:
            if isinstance(i, Video):
                subtitles = await self._video_to_subtitles(i)
            elif isinstance(i, Image):
                tasks.append(img2base64(i.path))
            else:
                ...

        result: list[str] = [
            i
            for i in await asyncio.gather(*tasks, return_exceptions=True)
            if not isinstance(i, BaseException)
        ]
        content = [
            {
                "type": "text",
                "text": (f"标题: {self.pr.title}" if self.pr.title else "")
                + (f"\n正文: {self.pr.desc}" if self.pr.desc else "")
                + (f"\n视频字幕: {subtitles}" if subtitles else ""),
            }
        ]
        imgs = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{i}"},
            }
            for i in result
        ]

        template = [
            SystemMessage(PROMPT),
            HumanMessage(content=content + imgs),
            HumanMessage(content=[{"type": "text", "text": "请对以上内容进行总结！"}]),
        ]

        llm = LLM(ph_cfg.provider, ph_cfg.api_key, ph_cfg.base_url, ph_cfg.model)
        model = llm.provider
        answer = await model.ainvoke(template)
        return SummaryResult(answer.content)

    @staticmethod
    async def _video_to_subtitles(media_: Media) -> str:
        if not media_.subtitles:
            tr = await Transcriptions(
                api_key=ph_cfg.api_key, base_url=ph_cfg.base_url
            ).transcription(media_.path)
            media_.subtitles = Subtitles(
                [
                    Subtitle(begin=str(c.begin), end=str(c.end), text=c.text)
                    for c in tr.chucks
                ]
            )
        if not media_.subtitles.subtitles[5:]:  # 小于5条字幕，直接过滤掉
            return ""
        return media_.subtitles.to_str()
