from dataclasses import dataclass
from typing import Self, cast

from parsehub.types import Platform
from pyrogram import Client, filters
from pyrogram.enums import ButtonStyle
from pyrogram.types import CallbackQuery, Message
from pyrogram.types import InlineKeyboardButton as Ikb
from pyrogram.types import InlineKeyboardMarkup as Ikm

from db import get_session
from repo import UserSettingsRepo, UsersRepo
from repo.user_settings import DefaultMode


@dataclass
class CQData:
    key: str
    """键放在最前面, 可用 filters.regex(r"^key") 过滤"""
    value: str
    """值"""
    uid: int
    """user id"""

    @classmethod
    def parse(cls, data: str | bytes) -> Self:
        key, value, uid = str(data).split(",")
        return cls(key=key, value=value, uid=int(uid))

    def unparse(self) -> str:
        return f"{self.key},{self.value},{self.uid}"

    def __str__(self) -> str:
        return self.unparse()

    def __repr__(self) -> str:
        return self.__str__()


LANG_MAP = {
    "zh-hans": "简体中文",
    "zh-hant": "繁体中文",
    "en-us": "English",
    "ja-jp": "日本語",
}


@Client.on_message(filters.command("lang"))
async def select_lang(_: Client, msg: Message) -> None:
    if not msg.from_user:
        return

    async with get_session() as session:
        ur = UsersRepo(session)
        user = await ur.get_or_create_by_telegram_user_id(msg.from_user.id)

    current_lang = user.language_code

    ikbs = [
        Ikb(
            v,
            callback_data=CQData(key="lang", value=k, uid=msg.from_user.id).unparse(),
            style=ButtonStyle.SUCCESS if k == current_lang else ButtonStyle.DEFAULT,
        )
        for k, v in LANG_MAP.items()
    ]

    reply_markup = Ikm([ikbs[i : i + 2] for i in range(0, len(ikbs), 2)])
    await msg.reply_text("**▎选择语言**", reply_markup=reply_markup)


@Client.on_callback_query(filters.regex(r"^lang"))
async def selected_lang(_: Client, cq: CallbackQuery) -> None:
    if not cq.data:
        return
    cqdata = CQData.parse(cq.data)
    if cq.from_user.id != cqdata.uid:
        await cq.answer("这不是你的操作", show_alert=True)
        return

    selected = cqdata.value
    async with get_session() as session:
        user = await UsersRepo(session).get_by_telegram_user_id(cq.from_user.id)
        if not user:
            raise ValueError("User not found")
        user.language_code = selected

    await cq.message.edit(f"**▎已切换为: {LANG_MAP[selected]}**")


MODE_MAP = {
    "preview": "预览",
    "raw": "原始",
    "zip": "压缩",
}


@Client.on_message(filters.command("mode"))
async def select_mode(_: Client, msg: Message) -> None:
    """设置默认解析模式"""
    if not msg.from_user:
        return

    async with get_session() as session:
        usr = UserSettingsRepo(session)
        user_config = await usr.get_config(msg.from_user.id)

    ikbs = [
        Ikb(
            v,
            callback_data=CQData(uid=msg.from_user.id, key="mode", value=k).unparse(),
            style=ButtonStyle.SUCCESS if k == user_config.default_mode else ButtonStyle.DEFAULT,
        )
        for k, v in MODE_MAP.items()
    ]
    reply_markup = Ikm([ikbs])
    await msg.reply_text("**▎选择默认解析模式**", reply_markup=reply_markup)


@Client.on_callback_query(filters.regex(r"^mode"))
async def selected_mode(_: Client, cq: CallbackQuery) -> None:
    if not cq.data:
        return

    cqdata = CQData.parse(cq.data)
    if cq.from_user.id != cqdata.uid:
        await cq.answer("这不是你的操作", show_alert=True)
        return

    selected = cast(DefaultMode, cqdata.value)
    async with get_session() as session:
        usr = UserSettingsRepo(session)
        user_config = await usr.get_config(cq.from_user.id)
        user_config.default_mode = selected
        await usr.save_config(cq.from_user.id, user_config)

    await cq.message.edit(f"**▎已切换为: {MODE_MAP[selected]}**")


@Client.on_message(filters.command("switch_auto_delete"))
async def switch_auto_delete_url(_: Client, msg: Message) -> None:
    if not msg.from_user:
        return

    async with get_session() as session:
        usr = UserSettingsRepo(session)
        user_config = await usr.get_config(msg.from_user.id)
        user_config.auto_delete_url = not user_config.auto_delete_url
        await usr.save_config(msg.from_user.id, user_config)

    await msg.reply_text(f"**▎已 {'启用' if user_config.auto_delete_url else '禁用'} 自动删除分享链接消息**")


@Client.on_message(filters.command("switch_platform"))
async def switch_platform(_: Client, msg: Message) -> None:
    if not msg.from_user:
        return

    async with get_session() as session:
        usr = UserSettingsRepo(session)
        user_config = await usr.get_config(msg.from_user.id)

    ikbs = [
        Ikb(
            p.display_name,
            callback_data=CQData(key="switch_platform", value=p.id, uid=msg.from_user.id).unparse(),
            style=ButtonStyle.DANGER if p.id in user_config.disabled_platforms else ButtonStyle.SUCCESS,
        )
        for p in list(Platform)
    ]
    reply_markup = Ikm([ikbs[i : i + 2] for i in range(0, len(ikbs), 2)])
    await msg.reply_text("**▎启用 / 禁用 要解析的平台**", reply_markup=reply_markup)


@Client.on_callback_query(filters.regex(r"^switch_platform"))
async def switch_platform_callback(_: Client, cq: CallbackQuery) -> None:
    if not cq.data:
        return

    cqdata = CQData.parse(cq.data)
    if cq.from_user.id != cqdata.uid:
        await cq.answer("这不是你的操作", show_alert=True)
        return

    selected = cqdata.value
    async with get_session() as session:
        usr = UserSettingsRepo(session)
        user_config = await usr.get_config(cq.from_user.id)
        if selected in user_config.disabled_platforms:
            user_config.disabled_platforms.remove(selected)
        else:
            user_config.disabled_platforms.append(selected)
        await usr.save_config(cq.from_user.id, user_config)

    ikbs = [
        Ikb(
            p.display_name,
            callback_data=CQData(key="switch_platform", value=p.id, uid=cqdata.uid).unparse(),
            style=ButtonStyle.DANGER if p.id in user_config.disabled_platforms else ButtonStyle.SUCCESS,
        )
        for p in list(Platform)
    ]
    reply_markup = Ikm([ikbs[i : i + 2] for i in range(0, len(ikbs), 2)])
    await cq.message.edit_reply_markup(reply_markup)
