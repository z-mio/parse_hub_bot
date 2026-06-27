from typing import Any

from pyrogram import filters
from pyrogram.types import InlineQuery, Message

from services import ParseService


async def _platform_filter(_: Any, __: Any, update: Message | InlineQuery) -> bool:
    t: str | None = None
    match update:
        case Message():
            t = update.caption or update.text
        case InlineQuery():
            t = update.query
    try:
        return bool(t and ParseService().parser.get_platform(t))
    except Exception:
        return False


platform_filter = filters.create(_platform_filter)


async def _via_me(_: Any, __: Any, update: Message) -> bool:
    return bool(update.via_bot and update.via_bot.is_self)


via_me_filter = filters.create(_via_me)
