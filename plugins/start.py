from pyrogram import Client, filters
from pyrogram.types import LinkPreviewOptions, Message

from db import get_session
from plugins.helpers import build_start_text
from services import AccountService


@Client.on_message(filters.command(["start", "help"]))
async def start(_: Client, msg: Message) -> None:
    if not msg.from_user:
        return

    async with get_session() as session:
        current = await AccountService(session, msg.from_user.id).ensure_account()

    await msg.reply(
        build_start_text()[current.lang],
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )
