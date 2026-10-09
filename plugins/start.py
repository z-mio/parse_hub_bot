from pyrogram import Client, filters
from pyrogram.types import LinkPreviewOptions, Message

from db import get_session
from plugins.helpers import build_help_rich_message, build_start_text
from services import UserService


async def _get_lang(user_id: int) -> str:
    async with get_session() as session:
        return await UserService(session).get_lang(user_id)


@Client.on_message(filters.command("start"))
async def start(_: Client, msg: Message) -> None:
    if not msg.from_user:
        return

    await msg.reply(
        build_start_text()[await _get_lang(msg.from_user.id)],
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


@Client.on_message(filters.command("help"))
async def help_(cli: Client, msg: Message) -> None:
    if not msg.from_user or msg.chat is None or msg.chat.id is None:
        return

    await cli.send_rich_message(
        chat_id=msg.chat.id,
        rich_message=build_help_rich_message(await _get_lang(msg.from_user.id)),
    )
