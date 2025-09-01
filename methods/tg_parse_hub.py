import asyncio
import re
import tempfile
from datetime import datetime, timedelta

import httpx
from abc import ABC, abstractmethod
from typing import Union, Callable
from aiocache import Cache
from aiocache.plugins import TimingPlugin
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from parsehub.config import ParseConfig, DownloadConfig
from pyrogram import enums, Client
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup as Ikm,
    InlineKeyboardButton as Ikb,
    InputMediaPhoto,
    InputMediaVideo,
    InlineQuery,
    InlineQueryResultPhoto,
    InlineQueryResultAnimation,
    CallbackQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    LinkPreviewOptions,
)

from parsehub import ParseHub
from parsehub.types import (
    ParseResult,
    Image,
    Video,
    Ani,
    VideoParseResult,
    ImageParseResult,
    MultimediaParseResult,
    SummaryResult,
    DownloadResult,
)
from parsehub.parsers.parser import WXImageParseResult, CoolapkImageParseResult
from parsehub.parsers.base import Parser
from config.config import bot_cfg
from config.platform_config import platforms_config, Platform
from utiles.converter import clean_article_html
from utiles.img_host import ImgHost
from utiles.ph import Telegraph
from utiles.utile import encrypt
from contextlib import asynccontextmanager
from markdown import markdown

_parsing = Cache(Cache.MEMORY, plugins=[TimingPlugin()])  # 正在解析的链接
_url_cache = Cache(Cache.MEMORY, plugins=[TimingPlugin()])  # 网址缓存
_operate_cache = Cache(Cache.MEMORY, plugins=[TimingPlugin()])  # 解析结果缓存
_msg_cache = Cache(Cache.MEMORY, plugins=[TimingPlugin()])  # 解析结果消息缓存

scheduler = AsyncIOScheduler()
scheduler.start()


class TgParseHub(ParseHub):
    """重新封装 ParseHub 类，使其适用于 Telegram"""

    def __init__(self):
        super().__init__()
        self.url = None
        self.platform: Parser | None = None
        self.platform_config: Platform | None = None
        self.parser_config: ParseConfig | None = None
        self.downloader_config: DownloadConfig | None = None

        self.is_cache = bool(bot_cfg.cache_time)
        self.parsing = _parsing
        """正在解析的链接"""
        self.cache = _operate_cache
        """解析结果缓存"""
        self.url_cache = _url_cache
        """网址缓存"""
        self.operate: ParseResultOperate | None = None
        """解析结果操作对象"""

    async def init_parser(self, url: str):
        self.url = await self._get_url(url)
        if not self.url:
            raise ValueError("未获取到链接")

        self.platform = self.select_parser(self.url)
        if not self.platform:
            raise ValueError("不支持的平台/内容")

        self.platform_config = platforms_config.platforms.get(
            self.platform.__platform_id__
        )
        if self.platform_config:
            self.parser_config = ParseConfig(
                proxy=(self.platform_config.parser_proxy or bot_cfg.parser_proxy)
                if not self.platform_config.disable_parser_proxy
                else None,
                cookie=self.platform_config.cookie,
            )
            self.downloader_config = DownloadConfig(
                proxy=(
                    self.platform_config.downloader_proxy or bot_cfg.downloader_proxy
                )
                if not self.platform_config.disable_downloader_proxy
                else None,
            )
        else:
            self.parser_config = ParseConfig(proxy=bot_cfg.parser_proxy)
            self.downloader_config = DownloadConfig(proxy=bot_cfg.downloader_proxy)
        self.config = self.parser_config

    async def parse(
        self, url: str, cache_time: int = bot_cfg.cache_time
    ) -> "TgParseHub":
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

    async def download(
        self, callback: Callable = None, callback_args: tuple = ()
    ) -> DownloadResult:
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
            await self.cache.delete(self.operate.hash_url)
        self.operate.delete()

    async def chat_upload(
        self, cli: Client, msg: Message
    ) -> Message | list[Message] | list[list[Message]]:
        """发送解析结果到聊天中"""

        async def handle_cache(m):
            if isinstance(m, Message):
                return await m.copy(msg.chat.id)
            if isinstance(m, list):
                if all(isinstance(i, Message) for i in m):
                    if not m:
                        return None
                    m = m[0]
                    mg = await cli.copy_media_group(msg.chat.id, m.chat.id, m.id)

                    return mg
                [await handle_cache(i) for i in m]
                await msg.reply(
                    self.operate.content_and_no_url,
                    quote=False,
                    reply_markup=self.operate.button(),
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                )

        cache_msg = await self._get_msg_cache()
        if cache_msg:
            return await handle_cache(cache_msg)

        async with self.error_handler():
            msg = await self.operate.chat_upload(msg)

        if self.is_cache:
            await self._set_msg_cache(msg)
        else:
            await self.delete()
        await self._del_parse_task()
        return msg

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
        return await self.parsing.get(url)

    async def _get_parse_task(self):
        """获取解析任务"""
        return await self.parsing.get(self.url, False)

    async def _add_parse_task(self):
        """添加解析任务, 超时: 5分钟"""
        await self.parsing.set(self.url, True, ttl=300)

    async def _del_parse_task(self):
        """解析结束"""
        await self.parsing.delete(self.url)

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
        await self.url_cache.set(encrypt(self.url), self.url, ttl=bot_cfg.cache_time)

    async def _get_url_cache(self, hash_url: str) -> str | None:
        """获取缓存网址"""
        return await self.url_cache.get(hash_url)

    async def _get_cache(self) -> Union["ParseResultOperate", None]:
        """获取缓存结果"""
        return await self.cache.get(encrypt(self.url))

    async def _set_cache(self, result: "ParseResultOperate", cache_time):
        """缓存结果"""
        await self.cache.set(result.hash_url, result)
        await self._clear_cache(cache_time)

    async def _clear_cache(self, cache_time: int = bot_cfg.cache_time):
        """定时删除缓存"""

        async def fn():
            await self.cache.delete(self.operate.hash_url)
            self.operate.delete()

        if not scheduler.get_job(self.operate.hash_url):
            run_time = datetime.now() + timedelta(seconds=cache_time)
            scheduler.add_job(fn, "date", run_date=run_time, id=self.operate.hash_url)

    async def _get_msg_cache(
        self,
    ) -> Message | list[Message] | list[list[Message]] | None:
        """获取缓存消息"""
        return await _msg_cache.get(self.operate.hash_url)

    async def _set_msg_cache(self, msg: Message):
        """缓存消息"""
        await _msg_cache.set(self.operate.hash_url, msg, ttl=bot_cfg.cache_time)

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
    async def chat_upload(
        self, msg: Message
    ) -> Message | list[Message] | list[list[Message]]:
        """普通聊天上传"""
        raise NotImplementedError

    async def inline_upload(self, iq: InlineQuery):
        """内联上传"""
        results = []

        media = (
            self.result.media
            if isinstance(self.result.media, list)
            else [self.result.media]
        )
        if not media:
            results.append(
                InlineQueryResultArticle(
                    title=self.result.title or "无标题",
                    description=self.result.desc,
                    input_message_content=InputTextMessageContent(
                        self.content_and_no_url,
                        link_preview_options=LinkPreviewOptions(is_disabled=True),
                    ),
                    reply_markup=self.button(),
                )
            )
        for index, i in enumerate(media):
            text = self.content_and_no_url
            k = {
                "caption": text,
                "title": text,
                "reply_markup": self.button(),
            }

            if isinstance(i, Image):
                results.append(
                    InlineQueryResultPhoto(
                        i.path,
                        photo_width=300,
                        photo_height=300,
                        **k,
                    )
                )
            elif isinstance(i, Video):
                results.append(
                    InlineQueryResultPhoto(
                        i.thumb_url
                        or "https://telegra.ph/file/cdfdb65b83a4b7b2b6078.png",
                        photo_width=300,
                        photo_height=300,
                        id=f"download_{index}",
                        title=text,
                        caption=text,
                        reply_markup=self.button(hide_summary=True),
                    )
                )
            elif isinstance(i, Ani):
                results.append(
                    InlineQueryResultAnimation(i.path, thumb_url=i.thumb_url, **k)
                )
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
            return
        button = []

        raw_url_btn = Ikb("原链接", url=self.result.raw_url)

        if show_summary_result:
            ai_summary_btn = Ikb("AI总结✅", callback_data=f"unsummary_{self.hash_url}")
        else:
            ai_summary_btn = Ikb("AI总结❎", callback_data=f"summary_{self.hash_url}")

        button.append(raw_url_btn)
        if bot_cfg.ai_summary and not hide_summary:
            if summarizing:
                ai_summary_btn = Ikb(
                    "AI总结中❇️", callback_data=f"summarizing_{self.hash_url}"
                )
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
                self.content_and_no_url,
                reply_markup=self.button(summarizing=True),
            )
            if not self.download_result:
                self.download_result = await self.result.download()
            try:
                r = await self.download_result.summary()
            except Exception as e:
                await cq.edit_message_text(
                    self.content_and_no_url,
                    reply_markup=self.button(),
                )
                raise e
            self.ai_summary_result = r

        await cq.edit_message_text(
            self.f_text(r.content), reply_markup=self.button(show_summary_result=True)
        )

        return self

    async def un_ai_summary(self, cq: CallbackQuery):
        """取消 AI 总结"""

        await cq.edit_message_text(self.content_and_no_url, reply_markup=self.button())

    @property
    def content_and_no_url(self) -> str:
        return (
            f"[{self.result.title or '无标题'}]({self.telegraph_url})"
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
        return self.f_text(
            f"{text}\n\n<b>> 原文链接: [LINK]({self.result.raw_url})</b>"
            if self.result.raw_url
            else text
        ).strip()

    @staticmethod
    def f_text(text: str) -> str:
        """格式化输出内容, 限制长度, 添加折叠块样式"""
        text = text.strip()
        if text[1020:]:
            text = text[:1000] + "..."
            return f"<blockquote expandable>{text}</blockquote>"
        elif text[500:] or len(text.splitlines()) > 10:
            # 超过 500 字或超过 10 行, 则添加折叠块样式
            return f"<blockquote expandable>{text}</blockquote>"
        else:
            return text


class VideoParseResultOperate(ParseResultOperate):
    """视频解析结果操作"""

    async def chat_upload(self, msg: Message) -> Message:
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            if self.result.media.thumb_url:
                async with httpx.AsyncClient() as client:
                    thumb = await client.get(self.result.media.thumb_url)
                    temp_file.write(thumb.content)
                    temp = temp_file.name
            else:
                temp = None

            await msg.reply_chat_action(enums.ChatAction.UPLOAD_VIDEO)
            return await msg.reply_video(
                self.download_result.media.path,
                caption=self.content_and_no_url,
                thumb=temp,
                quote=True,
                reply_markup=self.button(),
            )


class ImageParseResultOperate(ParseResultOperate):
    """图片解析结果操作"""

    async def _send_ph(self, html_content: str, msg: Message) -> Message:
        page = await Telegraph().create_page(
            self.result.title or "无标题", html_content=html_content
        )
        self.telegraph_url = page.url
        return await msg.reply_text(
            self.content_and_no_url,
            quote=True,
            reply_markup=self.button(),
        )

    async def chat_upload(
        self, msg: Message
    ) -> Message | list[Message] | list[list[Message]]:
        await msg.reply_chat_action(enums.ChatAction.UPLOAD_PHOTO)

        if isinstance(self.result, WXImageParseResult):
            return await self._send_ph(
                clean_article_html(
                    markdown(
                        self.result.wx.markdown_content.replace(
                            "mmbiz.qpic.cn", "mmbiz.qpic.cn.in"
                        )
                    )
                ),
                msg,
            )
        elif isinstance(self.result, CoolapkImageParseResult) and (
            markdown_content := self.result.coolapk.markdown_content
        ):
            return await self._send_ph(
                clean_article_html(
                    markdown(
                        markdown_content.replace(
                            "image.coolapk.com", "qpic.cn.in/image.coolapk.com"
                        )
                    )
                ),
                msg,
            )

        count = len(self.download_result.media)
        text = self.content_and_no_url
        if count == 0:
            return await msg.reply_text(
                text,
                quote=True,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
                reply_markup=self.button(),
            )
        elif count == 1:
            return await msg.reply_photo(
                self.download_result.media[0].path,
                quote=True,
                caption=text,
                reply_markup=self.button(),
            )
        elif count <= 9:
            text = self.content_and_no_url
            m = await msg.reply_media_group(
                [InputMediaPhoto(v.path) for v in self.download_result.media]
            )
            await m[0].reply_text(
                text,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
                reply_markup=self.button(),
                quote=True,
            )
            return [m]
        else:
            ih = ImgHost()
            tasks = [ih.litterbox(i.path) for i in self.download_result.media]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            results = [
                f'<img src="{i}">' for i in results if not isinstance(i, Exception)
            ]
            if not results:
                return await msg.reply_text("图片上传图床失败")
            return await self._send_ph(
                f"{self.result.desc}<br><br>" + "".join(results), msg
            )


class MultimediaParseResultOperate(ParseResultOperate):
    """图片视频混合解析结果操作"""

    async def chat_upload(
        self, msg: Message
    ) -> Message | list[Message] | list[list[Message]]:
        await msg.reply_chat_action(enums.ChatAction.UPLOAD_PHOTO)

        count = len(self.download_result.media)
        text = self.content_and_no_url
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
                return await msg.reply_photo(m.path, **k)
            elif isinstance(m, Video):
                return await msg.reply_video(m.path, **k)
            elif isinstance(m, Ani):
                return await msg.reply_animation(m.path, **k)

        else:
            text = self.content_and_no_url
            media = []
            ani_msg = []
            for i, v in enumerate(self.download_result.media):
                if isinstance(v, Image):
                    media.append(InputMediaPhoto(v.path))
                elif isinstance(v, Video):
                    media.append(InputMediaVideo(v.path))
                elif isinstance(v, Ani):
                    ani = await msg.reply_animation(
                        v.path,
                        quote=True,
                        caption=text if not i else f"**{i + 1}/{count}**",
                    )
                    ani_msg.append(ani)
            m = ani_msg + [
                await msg.reply_media_group(media[i : i + 10], quote=True)
                for i in range(0, count, 10)
            ]
            mm = m[0][0] if isinstance(m[0], list) else m[0]
            await mm.reply_text(
                text,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
                reply_markup=self.button(),
                quote=True,
            )
            return m
