import asyncio
import os
import re
import shutil
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import BinaryIO, Union

from aiocache import SimpleMemoryCache
from aiocache.plugins import TimingPlugin
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from markdown import markdown
from parsehub import ParseHub
from parsehub.config import DownloadConfig, ParseConfig
from parsehub.parsers.base import BaseParser
from parsehub.parsers.parser import CoolapkImageParseResult, WXImageParseResult
from parsehub.types import (
    Ani,
    DownloadResult,
    Image,
    ImageParseResult,
    MultimediaParseResult,
    ParseResult,
    SummaryResult,
    Video,
    VideoParseResult,
)
from pyrogram import Client, enums
from pyrogram.types import (
    CallbackQuery,
    InlineQuery,
    InlineQueryResultAnimation,
    InlineQueryResultArticle,
    InlineQueryResultPhoto,
    InlineQueryResultVideo,
    InputMediaPhoto,
    InputMediaVideo,
    InputTextMessageContent,
    LinkPreviewOptions,
    Message,
)
from pyrogram.types import (
    InlineKeyboardButton as Ikb,
)
from pyrogram.types import (
    InlineKeyboardMarkup as Ikm,
)

from config.config import TEMP_DIR, bot_cfg
from config.platform_config import Platform, platforms_config
from log import logger
from utiles.converter import clean_article_html
from utiles.img_host import ImgHost
from utiles.ph import Telegraph
from utiles.utile import encrypt, img2webp, split_video

CACHE = SimpleMemoryCache(plugins=[TimingPlugin()])

scheduler = AsyncIOScheduler()
scheduler.start()


@dataclass
class CachedMessageInfo:
    """缓存的消息信息"""

    chat_id: int
    message_id: int
    is_media_group: bool = False


class TgParseHub(ParseHub):
    """重新封装 ParseHub 类，使其适用于 Telegram"""

    def __init__(self):
        super().__init__()
        self.url = None
        self.platform: BaseParser | None = None
        self.platform_config: Platform | None = None
        self.parser_config: ParseConfig | None = None
        self.downloader_config: DownloadConfig | None = None

        self.is_cache = bool(bot_cfg.cache_time)
        self.cache = CACHE
        self.operate: ParseResultOperate | None = None
        """解析结果操作对象"""

    async def init_parser(self, url: str):
        self.url = await self._get_url(url)
        if not self.url:
            raise ValueError("未获取到链接")

        self.platform = self.select_parser(self.url)
        if not self.platform:
            raise ValueError("不支持的平台/内容")

        self.platform_config = platforms_config.platforms.get(self.platform.__platform_id__)
        if self.platform_config:
            self.parser_config = ParseConfig(
                proxy=(self.platform_config.parser_proxy or bot_cfg.parser_proxy)
                if not self.platform_config.disable_parser_proxy
                else None,
                cookie=self.platform_config.cookie,
            )
            self.downloader_config = DownloadConfig(
                proxy=(self.platform_config.downloader_proxy or bot_cfg.downloader_proxy)
                if not self.platform_config.disable_downloader_proxy
                else None,
            )
        else:
            self.parser_config = ParseConfig(proxy=bot_cfg.parser_proxy)
            self.downloader_config = DownloadConfig(proxy=bot_cfg.downloader_proxy)
        self.config = self.parser_config

    async def parse(self, url: str, cache_time: int = bot_cfg.cache_time) -> "TgParseHub":
        """
        解析网址，并返回解析结果操作对象。
        :param url: url 或 hash后的url
        :param cache_time: 缓存时间, 默认缓存一天
        :return:
        """
        await self.init_parser(url)
        while await self._get_parse_task():
            await asyncio.sleep(1)

        if not (operate := await self._get_cache()):
            await self._add_parse_task()
            async with self.error_handler():
                r = await super().parse(self.url)
            operate = self._select_operate(r)

        self.operate = operate
        if self.is_cache:
            """缓存结果"""
            await self._set_cache(operate, cache_time)
        if bot_cfg.ai_summary:
            """开启 AI 总结"""
            await self._set_url_cache()

        return self

    async def ai_summary(self, cq: CallbackQuery):
        """获取 AI 总结"""
        self.operate = await self.operate.ai_summary(cq)
        await self._set_cache(self.operate, bot_cfg.cache_time)

    async def un_ai_summary(self, cq: CallbackQuery):
        """取消 AI 总结"""
        return await self.operate.un_ai_summary(cq)

    async def download(self, callback: Callable = None, callback_args: tuple = ()) -> DownloadResult:
        if (dr := self.operate.download_result) and dr.exists():
            return dr
        async with self.error_handler():
            self.operate.download_result = await self.result.download(
                None, callback, callback_args, config=self.downloader_config
            )
        return self.operate.download_result

    async def delete(self):
        """删除文件"""
        if not self.operate:
            return
        if self.is_cache:
            await self.cache.delete(f"parse:result:{self.operate.hash_url}")
        self.operate.delete()

    async def chat_upload(self, cli: Client, msg: Message) -> Message | list[Message] | list[list[Message]]:
        """发送解析结果到聊天中"""

        # 检查缓存
        if cached_info := await self._get_msg_cache():
            if reconstructed := await self._reconstruct_messages(
                cli, cached_info, msg.chat.id, msg.id, msg.message_thread_id
            ):
                return reconstructed

        # 没有缓存则执行实际上传
        async with self.error_handler():
            result_msg = await self.operate.chat_upload(msg)

        # 缓存消息信息
        if self.is_cache:
            await self._set_msg_cache(result_msg)
        else:
            await self.delete()
        await self._del_parse_task()
        return result_msg

    async def inline_upload(self, iq: InlineQuery):
        """发送解析结果到内联中"""
        async with self.error_handler():
            await self.operate.inline_upload(iq)
        await self._del_parse_task()

    @asynccontextmanager
    async def error_handler(self):
        try:
            yield
        except Exception as e:
            await self._error_callback()
            raise e

    async def _error_callback(self):
        """错误回调"""
        await self._del_parse_task()
        await self.delete()

    async def get_parse_task(self, url: str) -> bool:
        """获取解析任务"""
        url = await self._get_url(url)
        return await self.cache.get(f"parse:parsing:{url}")

    async def _get_parse_task(self):
        """获取解析任务"""
        return await self.cache.get(f"parse:parsing:{self.url}", False)

    async def _add_parse_task(self):
        """添加解析任务, 超时: 5分钟"""
        await self.cache.set(f"parse:parsing:{self.url}", True, ttl=300)

    async def _del_parse_task(self):
        """解析结束"""
        await self.cache.delete(f"parse:parsing:{self.url}")

    async def _get_url(self, url: str):
        """获取网址"""
        # 如果是 hash 链接，则从缓存中获取原始链接
        if re.match(r"[a-f0-9]{32}", url):
            if not (url := await self._get_url_cache(url)):
                return None
            return url
        return await self.get_raw_url(url)

    async def _set_url_cache(self):
        """缓存网址"""
        await self.cache.set(f"parse:url:{encrypt(self.url)}", self.url, ttl=bot_cfg.cache_time)

    async def _get_url_cache(self, hash_url: str) -> str | None:
        """获取缓存网址"""
        return await self.cache.get(f"parse:url:{hash_url}")

    async def _get_cache(self) -> Union["ParseResultOperate", None]:
        """获取缓存结果"""
        return await self.cache.get(f"parse:result:{encrypt(self.url)}")

    async def _set_cache(self, result: "ParseResultOperate", cache_time):
        """缓存结果"""
        await self.cache.set(f"parse:result:{result.hash_url}", result)
        await self._clear_cache(cache_time)

    async def _clear_cache(self, cache_time: int = bot_cfg.cache_time):
        """定时删除缓存"""

        async def fn():
            await self.cache.delete(f"parse:result:{self.operate.hash_url}")
            self.operate.delete()

        if not scheduler.get_job(self.operate.hash_url):
            run_time = datetime.now() + timedelta(seconds=cache_time)
            scheduler.add_job(fn, "date", run_date=run_time, id=self.operate.hash_url)

    async def _get_msg_cache(self) -> CachedMessageInfo | list[CachedMessageInfo] | None:
        """获取缓存的消息信息"""
        return await self.cache.get(f"parse:msg:{self.operate.hash_url}")

    async def _set_msg_cache(self, msg: Message | list[Message] | list[list[Message]]):
        """缓存消息ID信息"""
        cached_info = self._extract_msg_ids(msg)
        if cached_info:
            await self.cache.set(f"parse:msg:{self.operate.hash_url}", cached_info, ttl=bot_cfg.cache_time)

    @staticmethod
    def _extract_msg_ids(
        msg: Message | list[Message] | list[list[Message]],
    ) -> CachedMessageInfo | list[CachedMessageInfo] | None:
        """从消息中提取 chat_id 和 message_id 信息"""
        if isinstance(msg, Message):
            # 单条消息
            return CachedMessageInfo(chat_id=msg.chat.id, message_id=msg.id)
        elif isinstance(msg, list):
            if not msg:
                return None
            if all(isinstance(i, Message) for i in msg):
                # 媒体组：缓存第一条消息的ID
                return CachedMessageInfo(chat_id=msg[0].chat.id, message_id=msg[0].id, is_media_group=True)
            else:
                # 嵌套列表（多个媒体组）
                result = []
                for item in msg:
                    if isinstance(item, Message):
                        result.append(CachedMessageInfo(chat_id=item.chat.id, message_id=item.id))
                    elif isinstance(item, list) and item:
                        result.append(
                            CachedMessageInfo(chat_id=item[0].chat.id, message_id=item[0].id, is_media_group=True)
                        )
                return result if result else None
        return None

    async def _reconstruct_messages(
        self,
        cli: Client,
        cached_info: CachedMessageInfo | list[CachedMessageInfo],
        target_chat_id: int,
        target_message_id: int,
        message_thread_id: int | None = None,
    ) -> Message | list[Message] | list[list[Message]] | None:
        """根据缓存的消息ID信息重建消息并复制到目标聊天"""
        try:
            if isinstance(cached_info, CachedMessageInfo):
                # 单条消息或单个媒体组
                if cached_info.is_media_group:
                    # 复制媒体组
                    return await cli.copy_media_group(
                        target_chat_id,
                        cached_info.chat_id,
                        cached_info.message_id,
                        message_thread_id=message_thread_id,
                        reply_to_message_id=target_message_id,
                    )
                else:
                    # 复制单条消息
                    original_msg = await cli.get_messages(cached_info.chat_id, cached_info.message_id)
                    return await original_msg.copy(
                        target_chat_id, message_thread_id=message_thread_id, reply_to_message_id=target_message_id
                    )
            elif isinstance(cached_info, list):
                # 多个消息/媒体组
                results = []
                for info in cached_info:
                    if info.is_media_group:
                        mg = await cli.copy_media_group(
                            target_chat_id,
                            info.chat_id,
                            info.message_id,
                            message_thread_id=message_thread_id,
                            reply_to_message_id=target_message_id,
                        )
                        results.append(mg)
                    else:
                        original_msg = await cli.get_messages(info.chat_id, info.message_id)
                        copied = await original_msg.copy(
                            target_chat_id, message_thread_id=message_thread_id, reply_to_message_id=target_message_id
                        )
                        results.append(copied)
                    await asyncio.sleep(0.5)  # 避免速率限制

                # 发送文本说明消息
                if results:
                    first_msg = results[0][0] if isinstance(results[0], list) else results[0]
                    await first_msg.reply_text(
                        self.operate.content_and_url,
                        link_preview_options=LinkPreviewOptions(is_disabled=True),
                        reply_markup=self.operate.button(),
                        quote=True,
                    )
                return results
        except Exception as e:
            logger.warning(f"重建缓存消息失败: {e}")
            # 缓存失效，删除缓存
            await self.cache.delete(f"parse:msg:{self.operate.hash_url}")
            return None

    @staticmethod
    def _select_operate(result: ParseResult = None) -> "ParseResultOperate":
        """根据解析结果类型选择对应的操作类"""
        cls = result.__class__
        if issubclass(cls, VideoParseResult):
            op = VideoParseResultOperate
        elif issubclass(cls, ImageParseResult):
            op = ImageParseResultOperate
        elif issubclass(cls, MultimediaParseResult):
            op = MultimediaParseResultOperate
        else:
            raise ValueError("未知的 ParseResult 类型")
        return op(result)

    @property
    def result(self) -> ParseResult:
        return self.operate and self.operate.result


class ParseResultOperate(ABC):
    """解析结果操作基类"""

    def __init__(self, result: ParseResult):
        self.result = result
        self.download_result: DownloadResult | None = None
        self.ai_summary_result: SummaryResult | None = None
        self.telegraph_url: str | None = None  # telegraph 帖子链接

    @abstractmethod
    async def chat_upload(self, msg: Message) -> Message | list[Message] | list[list[Message]]:
        """普通聊天上传"""
        raise NotImplementedError

    async def inline_upload(self, iq: InlineQuery):
        """内联上传"""
        results = []

        media = self.result.media if isinstance(self.result.media, list) else [self.result.media]
        if not media:
            results.append(
                InlineQueryResultArticle(
                    title=self.result.title or "无标题",
                    description=self.result.desc,
                    input_message_content=InputTextMessageContent(
                        self.content_and_url,
                        link_preview_options=LinkPreviewOptions(is_disabled=True),
                    ),
                    reply_markup=self.button(),
                )
            )
        for index, i in enumerate(media):
            text = self.content_and_url
            k = {
                "caption": text,
                "title": self.result.title or "无标题",
                "description": self.result.desc,
                "reply_markup": self.button(),
            }

            if isinstance(i, Image):
                results.append(
                    InlineQueryResultPhoto(
                        i.path,
                        photo_width=i.width or 300,
                        photo_height=i.height or 300,
                        **k,
                    )
                )
            elif isinstance(i, Video):
                if i.exists() and os.path.getsize(i.path) > 1024 * 1024 * 2:
                    results.append(
                        InlineQueryResultPhoto(
                            i.thumb_url,
                            photo_width=i.width or 300,
                            photo_height=i.height or 300,
                            **k,
                        )
                    )
                else:
                    results.append(
                        InlineQueryResultPhoto(
                            i.thumb_url or "https://telegra.ph/file/cdfdb65b83a4b7b2b6078.png",
                            photo_width=i.width or 300,
                            photo_height=i.height or 300,
                            id=f"download_{index}",
                            title=text,
                            caption=text,
                            reply_markup=self.button(hide_summary=True),
                        )
                    )
            elif isinstance(i, Ani):
                if i.ext != "gif":
                    results.append(
                        InlineQueryResultVideo(
                            i.path,
                            i.thumb_url or "https://telegra.ph/file/cdfdb65b83a4b7b2b6078.png",
                            **k,
                        )
                    )
                else:
                    results.append(InlineQueryResultAnimation(i.path, thumb_url=i.thumb_url, **k))
        return await iq.answer(results, cache_time=0)

    def delete(self):
        """删除文件"""
        if not self.download_result:
            return
        self.download_result.delete()

    def button(
        self,
        hide_summary: bool = False,
        show_summary_result: bool = False,
        summarizing: bool = False,
    ) -> Ikm | None:
        """
        按钮
        :param hide_summary: 隐藏 AI 总结按钮
        :param show_summary_result: 显示 AI 总结结果
        :param summarizing: 总结中
        :return:
        """
        if not self.result.raw_url:
            return None
        button = []

        raw_url_btn = Ikb("原链接", url=self.result.raw_url)

        if show_summary_result:
            ai_summary_btn = Ikb("AI总结✅", callback_data=f"unsummary_{self.hash_url}")
        else:
            ai_summary_btn = Ikb("AI总结❎", callback_data=f"summary_{self.hash_url}")

        button.append(raw_url_btn)
        if bot_cfg.ai_summary and not hide_summary:
            if summarizing:
                ai_summary_btn = Ikb("AI总结中❇️", callback_data=f"summarizing_{self.hash_url}")
            button.append(ai_summary_btn)

        return Ikm([button])

    @property
    def hash_url(self):
        """网址哈希值"""
        return encrypt(self.result.raw_url)

    async def ai_summary(self, cq: CallbackQuery) -> "ParseResultOperate":
        """获取 AI 总结"""

        if not (r := self.ai_summary_result):
            await cq.edit_message_text(
                self.content_and_url,
                reply_markup=self.button(summarizing=True),
            )
            if not self.download_result:
                self.download_result = await self.result.download()
            try:
                r = await self.download_result.summary()
            except Exception as e:
                await cq.edit_message_text(
                    self.content_and_url,
                    reply_markup=self.button(),
                )
                raise e
            self.ai_summary_result = r

        await cq.edit_message_text(
            self.add_source(self.f_text(r.content)), reply_markup=self.button(show_summary_result=True)
        )

        return self

    async def un_ai_summary(self, cq: CallbackQuery):
        """取消 AI 总结"""

        await cq.edit_message_text(self.content_and_url, reply_markup=self.button())

    @property
    def content_and_no_url(self) -> str:
        return (
            f"[{self.result.title.replace('\n', ' ') or '无标题'}]({self.telegraph_url})"
            if self.telegraph_url
            else (
                self.f_text(f"**{self.result.title}**\n\n{self.result.desc}")
                if self.result.title or self.result.desc
                else "无标题"
            )
        ).strip()

    @property
    def content_and_url(self) -> str:
        text = self.content_and_no_url
        return self.add_source(text)

    def add_source(self, text: str):
        """添加链接"""
        return (f"{text}\n\n<b>▎[Source]({self.result.raw_url})</b>" if self.result.raw_url else text).strip()

    @staticmethod
    def f_text(text: str) -> str:
        """格式化输出内容, 限制长度, 添加折叠块样式"""
        text = text.strip()
        if text[1020:]:
            text = text[:1000] + "......"
            return f"<blockquote expandable>{text}</blockquote>"
        elif text[500:] or len(text.splitlines()) > 10:
            # 超过 500 字或超过 10 行, 则添加折叠块样式
            return f"<blockquote expandable>{text}</blockquote>"
        else:
            return text

    @staticmethod
    async def tg_compatible(img: str | Path) -> BinaryIO | str:
        """将图片转换为Tg兼容的格式"""

        ext = Path(img).suffix.lower()
        if ext not in [".heif", ".heic"]:
            return str(img)

        try:
            return await asyncio.to_thread(img2webp, img)
        except Exception as e:
            logger.exception(e)
            return str(img)


class VideoParseResultOperate(ParseResultOperate):
    """视频解析结果操作"""

    async def chat_upload(self, msg: Message) -> Message | list[list[Message]]:
        await msg.reply_chat_action(enums.ChatAction.UPLOAD_VIDEO)
        drm = self.download_result.media
        op = TEMP_DIR / f"{time.time_ns()}"
        op.mkdir(parents=True, exist_ok=True)
        try:
            handle_video = await self.handle_video(drm.path, op)
            if len(handle_video) == 1:
                m = await msg.reply_video(
                    str(handle_video[0]),
                    caption=self.content_and_url,
                    video_cover=drm.thumb_url,
                    quote=True,
                    reply_markup=self.button(),
                    width=drm.width or 0,
                    height=drm.height or 0,
                    duration=drm.duration or 0,
                )
                shutil.rmtree(str(op), ignore_errors=True)
                return m
            else:
                media = []
                for i, v in enumerate(handle_video):
                    media.append(
                        InputMediaVideo(
                            str(v),
                            video_cover=drm.thumb_url if i == 0 else None,
                            width=drm.width or 0,
                            height=drm.height or 0,
                        )
                    )
                m = [
                    await msg.reply_media_group(media[i : i + 10], quote=True) for i in range(0, len(handle_video), 10)
                ]
                mm = m[0][0] if isinstance(m[0], list) else m[0]
                await mm.reply_text(
                    self.content_and_url,
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                    reply_markup=self.button(),
                    quote=True,
                )
                shutil.rmtree(str(op), ignore_errors=True)
                return m
        except Exception as e:
            # 错误回退
            logger.exception(e)
            logger.error("上传视频失败, 以上为错误信息")
            shutil.rmtree(str(op), ignore_errors=True)
            if drm.thumb_url:
                return await msg.reply_photo(
                    photo=drm.thumb_url,
                    caption=self.content_and_url,
                    reply_markup=self.button(),
                    quote=True,
                )
            else:
                return await msg.reply_text(
                    self.content_and_url,
                    quote=True,
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                    reply_markup=self.button(),
                )

    @staticmethod
    async def handle_video(video: str | Path, op: Path) -> list[Path]:
        video_size = os.path.getsize(video)
        if video_size > 1024 * 1024 * 2:
            return await split_video(str(video), str(op))
        else:
            return [Path(video)]


class ImageParseResultOperate(ParseResultOperate):
    """图片解析结果操作"""

    async def _send_ph(self, html_content: str, msg: Message) -> Message:
        page = await Telegraph().create_page(self.result.title or "无标题", html_content=html_content)
        self.telegraph_url = page.url
        return await msg.reply_text(
            self.content_and_url,
            quote=True,
            reply_markup=self.button(),
        )

    async def chat_upload(self, msg: Message) -> Message | list[Message] | list[list[Message]]:
        await msg.reply_chat_action(enums.ChatAction.UPLOAD_PHOTO)

        if isinstance(self.result, WXImageParseResult):
            return await self._send_ph(
                clean_article_html(
                    markdown(self.result.wx.markdown_content.replace("mmbiz.qpic.cn", "mmbiz.qpic.cn.in"))
                ),
                msg,
            )
        elif isinstance(self.result, CoolapkImageParseResult) and (
            markdown_content := self.result.coolapk.markdown_content
        ):
            return await self._send_ph(
                clean_article_html(
                    markdown(markdown_content.replace("image.coolapk.com", "qpic.cn.in/image.coolapk.com"))
                ),
                msg,
            )

        count = len(self.download_result.media)
        text = self.content_and_url
        if count == 0:
            return await msg.reply_text(
                text,
                quote=True,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
                reply_markup=self.button(),
            )
        elif count == 1:
            return await msg.reply_photo(
                await self.tg_compatible(self.download_result.media[0].path),
                quote=True,
                caption=text,
                reply_markup=self.button(),
            )
        elif count <= 9:
            text = self.content_and_url
            m = await msg.reply_media_group(
                [InputMediaPhoto(await self.tg_compatible(v.path)) for v in self.download_result.media]
            )
            await m[0].reply_text(
                text,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
                reply_markup=self.button(),
                quote=True,
            )
            return [m]
        else:
            sem = asyncio.Semaphore(5)
            async with ImgHost() as ih:

                @logger.catch()
                async def limited_ih(path: str):
                    async with sem:
                        return await ih.zioooo(path)

                tasks = [limited_ih(i.path) for i in self.download_result.media]
                results = await asyncio.gather(*tasks, return_exceptions=True)
            results = [f'<img src="{i}">' for i in results if not isinstance(i, Exception)]
            if not results:
                return await msg.reply_text("图片上传图床失败")
            return await self._send_ph(f"{self.result.desc}<br><br>" + "".join(results), msg)


class MultimediaParseResultOperate(ParseResultOperate):
    """图片视频混合解析结果操作"""

    async def chat_upload(self, msg: Message) -> Message | list[Message] | list[list[Message]]:
        await msg.reply_chat_action(enums.ChatAction.UPLOAD_PHOTO)

        count = len(self.download_result.media)
        text = self.content_and_url
        if count == 0:
            return await msg.reply_text(
                text,
                quote=True,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
                reply_markup=self.button(),
            )
        elif count == 1:
            m = self.download_result.media[0]
            k = {
                "quote": True,
                "caption": text,
                "reply_markup": self.button(),
            }
            if isinstance(m, Image):
                return await msg.reply_photo(await self.tg_compatible(m.path), **k)
            elif isinstance(m, Video):
                return await msg.reply_video(
                    m.path,
                    video_cover=m.thumb_url,
                    width=m.width or 0,
                    height=m.height or 0,
                    duration=m.duration or 0,
                    **k,
                )
            elif isinstance(m, Ani):
                return await msg.reply_animation(m.path, **k)
            else:
                raise ValueError(f"未知的媒体类型: {type(m)}")

        else:
            text = self.content_and_url
            media = []
            ani_msg = []
            for i, v in enumerate(self.download_result.media):
                if isinstance(v, Image):
                    media.append(InputMediaPhoto(await self.tg_compatible(v.path)))
                elif isinstance(v, Video):
                    media.append(
                        InputMediaVideo(
                            v.path,
                            video_cover=v.thumb_url,
                            duration=v.duration or 0,
                            width=v.width or 0,
                            height=v.height or 0,
                        )
                    )
                elif isinstance(v, Ani):
                    ani = await msg.reply_animation(
                        v.path,
                        quote=True,
                        caption=f"**{i + 1}/{count}**",
                    )
                    ani_msg.append(ani)
            m = ani_msg + [await msg.reply_media_group(media[i : i + 10], quote=True) for i in range(0, count, 10)]
            mm = m[0][0] if isinstance(m[0], list) else m[0]
            await mm.reply_text(
                text,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
                reply_markup=self.button(),
                quote=True,
            )
            return m
