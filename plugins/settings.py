from pyrogram import Client, filters
from pyrogram.enums import ButtonStyle
from pyrogram.types import CallbackQuery, Message
from pyrogram.types import InlineKeyboardButton as Ikb
from pyrogram.types import InlineKeyboardMarkup as Ikm

from db import get_session
from repo import UserSettingsRepo, UsersRepo

LANG_MAP = {
    "zh-hans": "简体中文",
    "zh-hant": "繁体中文",
    "en-us": "English",
    "ja-jp": "日本語",
}


@Client.on_message(filters.command("set"))
async def settings(_: Client, msg: Message) -> None:
    if not msg.from_user:
        return

    async with get_session() as session:
        usr = UserSettingsRepo(session)
        user_config = await usr.get_config(msg.from_user.id)
    print(user_config)


@Client.on_message(filters.command("lang"))
async def select_lang(_: Client, msg: Message) -> None:
    if not msg.from_user:
        return

    async with get_session() as session:
        ur = UsersRepo(session)
        user = await ur.get_or_create_by_telegram_user_id(msg.from_user.id)

    current_lang = user.language_code

    def fn(v: str) -> str:
        return f"lang_{v}"

    ikbs = [
        Ikb(v, callback_data=fn(k), style=ButtonStyle.SUCCESS if k == current_lang else ButtonStyle.DEFAULT)
        for k, v in LANG_MAP.items()
    ]

    reply_markup = Ikm([ikbs[i : i + 2] for i in range(0, len(ikbs), 2)])
    await msg.reply_text("**▎选择语言**", reply_markup=reply_markup)


@Client.on_callback_query(filters.regex(r"^lang_"))
async def selected_lang(_: Client, cq: CallbackQuery) -> None:
    if not cq.data:
        return
    selected_lang_code: str = str(cq.data).split("_")[1]
    async with get_session() as session:
        user = await UsersRepo(session).get_by_telegram_user_id(cq.from_user.id)
        if not user:
            raise ValueError("User not found")
        user.language_code = selected_lang_code

    await cq.message.edit(f"**▎已切换为: {LANG_MAP[selected_lang_code]}**")
