from pyrogram import filters
from pyrogram.types import InlineQuery, Message

from services import ParseService


async def _platform_filter(_, __, update: Message | InlineQuery):
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
