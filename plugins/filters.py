from typing import Any

from pyrogram import filters
from pyrogram.types import InlineQuery, Message

from db.session import get_session
from repo import UserSettingsRepo
from services import ParseService


async def _platform_filter(_: Any, __: Any, update: Message | InlineQuery) -> bool:
    t: str | None = None
    match update:
        case Message():
            t = update.caption or update.text
        case InlineQuery():
            t = update.query

    try:
        platform = ParseService().parser.get_platform(t)
    except Exception:
        return False

    if not platform:
        return False

    if not update.from_user:
        return True

    async with get_session() as session:
        user_config = await UserSettingsRepo(session).get_config(update.from_user.id)
        if platform.id in user_config.disabled_platforms:
            return False
        return True


platform_filter = filters.create(_platform_filter)


async def _via_me(_: Any, __: Any, update: Message) -> bool:
    return bool(update.via_bot and update.via_bot.is_self)


via_me_filter = filters.create(_via_me)
