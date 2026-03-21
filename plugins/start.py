from pyrogram import Client, filters
from pyrogram.types import LinkPreviewOptions, Message

from plugins.helpers import build_start_text


@Client.on_message(filters.command(["start", "help"]))
async def start(_, msg: Message):
    await msg.reply(
        build_start_text(),
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )
