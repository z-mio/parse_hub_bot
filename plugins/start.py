from pyrogram import Client, filters
from pyrogram.types import Message

from db import get_session
from plugins.helpers import build_help_rich_message
from services import UserService


@Client.on_message(filters.command(["start", "help"]))
async def start(cli: Client, msg: Message) -> None:
    if not msg.from_user or msg.chat is None or msg.chat.id is None:
        return

    async with get_session() as session:
        lang = await UserService(session).get_lang(msg.from_user.id)

    await cli.send_rich_message(
        chat_id=msg.chat.id,
        rich_message=build_help_rich_message(lang),
    )
