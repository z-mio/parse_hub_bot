import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from easy_ai18n import PreLocaleSelector
from pyrogram import Client
from pyrogram.errors import FloodWait, Forbidden, SlowmodeWait
from pyrogram.types import LinkPreviewOptions, Message

from core import bs
from db import get_session
from log import logger
from plugins.context import get_config_target
from plugins.helpers import format_label
from plugins.parse.sender import MessageSender
from repo.settings import SettingsConfig
from services import SettingsService, StatusReporter

logger = logger.bind(name="ParseReporter")


async def disable_progress_on_report_forbidden(msg: Message, config: SettingsConfig) -> None:
    """状态消息无权限时自动关闭解析进度。"""
    config.noprogress = True
    target = get_config_target(msg, include_member=False)
    async with get_session() as session:
        await SettingsService(session).patch_config(target=target, noprogress=True)
    logger.warning(f"已自动关闭解析进度: {target}")


class MessageStatusReporter(StatusReporter):
    """基于 Telegram Message 的状态报告器"""

    def __init__(
        self,
        user_msg: Message,
        *,
        t: PreLocaleSelector,
        config: SettingsConfig,
        on_forbidden: Callable[[Message, SettingsConfig], Awaitable[None]] | None = None,
    ):
        self._user_msg = user_msg
        self._msg: Message | None = None
        self._t = t
        self._config = config
        self._on_forbidden = on_forbidden

    async def report(self, text: str) -> None:
        if self._config.noprogress:
            return
        await self._edit_text(format_label(text))

    async def report_error(self, stage: str, error: Exception) -> None:
        t = format_label(self._t(f"{stage}错误:"))
        text = self._t(f"{t} \n```\n{error}```")
        if bs.demo_mode:
            text += self._t("\n\n**问题反馈: @MisakaSisters**")
        await self._edit_text(
            text,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        if self._config.keep_error_log:
            return

        async def fn() -> None:
            await asyncio.sleep(15)
            await self.dismiss()

        loop = asyncio.get_running_loop()
        loop.create_task(fn())

    async def dismiss(self) -> None:
        if self._msg:
            await self._msg.delete()

    async def _edit_text(self, text: str, **kwargs: Any) -> None:
        try:
            if self._msg is None:
                self._msg = await MessageSender(self._user_msg, self._config).text(text, **kwargs)
            else:
                if self._msg.text != text:
                    await self._msg.edit_text(text, **kwargs)
        except (FloodWait, SlowmodeWait):
            pass
        except Forbidden as e:
            logger.warning(f"状态消息发送失败, Bot 无权限: {e}")
            if self._on_forbidden:
                await self._on_forbidden(self._user_msg, self._config)


class InlineStatusReporter(StatusReporter):
    """基于 inline_message_id 的状态报告器"""

    def __init__(
        self,
        cli: Client,
        inline_message_id: str,
        caption: str = "",
        *,
        t: PreLocaleSelector,
        user_config: SettingsConfig,
    ):
        self._cli = cli
        self._mid = inline_message_id
        self._caption = caption
        self._last_text: str | None = None
        self._t = t
        self._user_config = user_config

    async def report(self, text: str) -> None:
        text = format_label(text)
        full = f"{self._caption}\n{text}" if self._caption else text
        if full == self._last_text:
            return
        self._last_text = full
        await self._edit_inline_text(inline_message_id=self._mid, text=full)

    async def report_error(self, stage: str, error: Exception) -> None:
        text = self._t(f"{format_label(f'{stage}错误:')} \n```\n{error}```")
        if bs.demo_mode:
            text += self._t("\n\n**问题反馈: @MisakaSisters**")
        await self._edit_inline_text(
            inline_message_id=self._mid, text=text, link_preview_options=LinkPreviewOptions(is_disabled=True)
        )

        if self._user_config.keep_error_log:
            return

        async def fn() -> None:
            await asyncio.sleep(15)
            await self._edit_inline_text(
                inline_message_id=self._mid,
                text=self._caption,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )

        loop = asyncio.get_running_loop()
        loop.create_task(fn())

    async def _edit_inline_text(self, **kwargs: Any) -> None:
        try:
            await self._cli.edit_inline_text(**kwargs)
        except (FloodWait, SlowmodeWait):
            pass
        except Forbidden as e:
            logger.warning(f"消息发送失败, Bot 无权限: {e}")

    async def dismiss(self) -> None:
        pass
