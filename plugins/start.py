from pyrogram import Client, filters
from pyrogram.types import Message
from parsehub import ParseHub


@Client.on_message(filters.command(["start", "help"]))
async def start(_, msg: Message):
    await msg.reply(get_supported_platforms())


def get_supported_platforms():
    return "**支持的平台:**\n\n" + "\n".join(ParseHub().get_supported_platforms())
