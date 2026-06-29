from pyrogram import Client, filters
from pyrogram.types import LinkPreviewOptions, Message

from db import get_session
from plugins.helpers import build_start_text
from repo import UsersRepo


@Client.on_message(filters.command(["start", "help"]))
async def start(_: Client, msg: Message) -> None:
    if not msg.from_user:
        return

    async with get_session() as session:
        ur = UsersRepo(session)
        await ur.get_or_create_by_telegram_user_id(msg.from_user.id)

    await msg.reply(
        build_start_text(),
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )
