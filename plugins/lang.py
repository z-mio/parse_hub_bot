from pyrogram import Client, filters
from pyrogram.enums import ButtonStyle
from pyrogram.types import CallbackQuery, Message
from pyrogram.types import InlineKeyboardButton as Ikb
from pyrogram.types import InlineKeyboardMarkup as Ikm

from db import get_session
from i18n import LANG_MAP, t_
from plugins.helpers import format_label
from services import UserService


@Client.on_message(filters.command("lang"))
async def select_lang(_: Client, msg: Message) -> None:
    if not msg.from_user:
        return

    async with get_session() as session:
        lang = await UserService(session).get_lang(msg.from_user.id)

    ikbs = [
        Ikb(
            v,
            callback_data=f"lang|{msg.from_user.id}|{k}",
            style=ButtonStyle.PRIMARY if k == lang else ButtonStyle.DEFAULT,
        )
        for k, v in LANG_MAP.items()
    ]

    reply_markup = Ikm([ikbs[i : i + 2] for i in range(0, len(ikbs), 2)])
    await msg.reply_text(format_label("选择语言 / Select Language"), reply_markup=reply_markup)


@Client.on_callback_query(filters.regex(r"^lang"))
async def selected_lang(_: Client, cq: CallbackQuery) -> None:
    if not cq.data:
        return
    if not cq.message:
        return

    _key, uid, selected = str(cq.data).split("|", 2)
    if cq.from_user.id != int(uid):
        async with get_session() as session:
            lang = await UserService(session).get_lang(cq.from_user.id)
        await cq.answer(t_[lang]("这不是你的操作"), show_alert=True)
        return

    async with get_session() as session:
        user = await UserService(session).set_lang(cq.from_user.id, selected)

    await cq.message.edit(format_label(t_[user.language_code](f"已切换为: {LANG_MAP[selected]}")))
