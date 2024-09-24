from pyrogram import Client, filters
from pyrogram.types import Message

from config.config import HELP_TEXT


@Client.on_message(filters.command(["start", "help"]))
async def start(_, msg: Message):
    await msg.reply(HELP_TEXT)
