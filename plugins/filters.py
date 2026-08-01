from typing import Any

from pyrogram import Client, filters
from pyrogram.types import InlineQuery, Message, MessageOriginChannel, User

from db.session import get_session
from plugins.context import get_config_target
from services import ChannelSettingsTarget, ParseService, SettingsService


def platform_filter(use_config: bool = False) -> filters.Filter:
    """
    平台过滤器
    Args:
        use_config: 使用用户配置

    Returns:

    """

    async def func(flt: Any, __: Any, update: Message | InlineQuery) -> bool:
        t: str | None = None
        match update:
            case Message():
                t = update.caption or update.text
            case InlineQuery():
                t = update.query

        if not (platform := ParseService().parser.get_platform(t)):
            return False

        if flt.use_config is False:
            return True

        async with get_session() as session:
            target = get_config_target(update)
            config = await SettingsService(session).get_config(target)
            if platform.id in config.disabled_platforms:
                return False
            return True

    return filters.create(func, use_config=use_config)


async def _via_me(_: Any, __: Any, update: Message) -> bool:
    return bool(update.via_bot and update.via_bot.is_self)


via_me_filter = filters.create(_via_me)


async def _forwarded_from_bot(_: Any, __: Any, update: Message) -> bool:
    sender_user: User | None = getattr(update.forward_origin, "sender_user", None)
    if sender_user and sender_user.is_bot:
        return True
    return False


forwarded_from_bot_filter = filters.create(_forwarded_from_bot)
"""转发的 bot 消息"""


async def _allow_channel_auto_forward_parse_filter(_: Any, cli: Client, update: Message) -> bool:
    if not update.forward_origin:
        return True

    if not update.automatic_forward:
        return True

    if not isinstance(update.forward_origin, MessageOriginChannel):
        return True

    if not update.forward_origin.chat or not (cid := update.forward_origin.chat.id):
        return True

    try:
        await cli.get_chat_member(cid, "me")
    except Exception:
        return True

    if not (platform := ParseService().parser.get_platform(update.text)):
        return False

    async with get_session() as session:
        config = await SettingsService(session).get_config(ChannelSettingsTarget(telegram_chat_id=cid))
        if platform.id in config.disabled_platforms:
            return True
        return False


allow_channel_auto_forward_parse_filter = filters.create(_allow_channel_auto_forward_parse_filter)
"""判断群组中关联频道自动转发的消息是否允许解析, 避免与频道解析重复"""
