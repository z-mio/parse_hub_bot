from dataclasses import dataclass
from typing import Self, cast

from parsehub.types import Platform
from pyrogram import Client, filters
from pyrogram.enums import ButtonStyle
from pyrogram.types import CallbackQuery, Message
from pyrogram.types import InlineKeyboardButton as Ikb
from pyrogram.types import InlineKeyboardMarkup as Ikm

from db import get_session
from i18n import LANG_MAP, t_
from repo.user_settings import DefaultMode
from services import AccountContext, AccountService


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


@Client.on_message(filters.command("lang"))
async def select_lang(_: Client, msg: Message) -> None:
    if not msg.from_user:
        return

    async with get_session() as session:
        current = await AccountService(session, msg.from_user.id).ensure_account()

    current_lang = current.lang

    ikbs = [
        Ikb(
            v,
            callback_data=CQData(key="lang", value=k, uid=msg.from_user.id).unparse(),
            style=ButtonStyle.PRIMARY if k == current_lang else ButtonStyle.DEFAULT,
        )
        for k, v in LANG_MAP.items()
    ]

    reply_markup = Ikm([ikbs[i : i + 2] for i in range(0, len(ikbs), 2)])
    await msg.reply_text("**▎选择语言 / Select Language**", reply_markup=reply_markup)


@Client.on_callback_query(filters.regex(r"^lang"))
async def selected_lang(_: Client, cq: CallbackQuery) -> None:
    if not cq.data:
        return

    cqdata = CQData.parse(cq.data)
    if cq.from_user.id != cqdata.uid:
        async with get_session() as session:
            lang = await AccountService(session, cq.from_user.id).get_lang()
        await cq.answer(t_[lang]("这不是你的操作"), show_alert=True)
        return

    selected = cqdata.value
    async with get_session() as session:
        current = await AccountService(session, cq.from_user.id).set_language(selected)

    await cq.message.edit(t_[current.lang](f"**▎已切换为: {LANG_MAP[selected]}**"))


MODE_MAP = {
    "preview": t_("预览"),
    "raw": t_("原始"),
    "zip": t_("压缩"),
}


@Client.on_message(filters.command("mode"))
async def select_mode(_: Client, msg: Message) -> None:
    """设置默认解析模式"""
    if not msg.from_user:
        return

    async with get_session() as session:
        current = await AccountService(session, msg.from_user.id).ensure_account()
        lang = current.lang
        user_config = current.config

    ikbs = [
        Ikb(
            v[lang],
            callback_data=CQData(uid=msg.from_user.id, key="mode", value=k).unparse(),
            style=ButtonStyle.PRIMARY if k == user_config.default_mode else ButtonStyle.DEFAULT,
        )
        for k, v in MODE_MAP.items()
    ]
    reply_markup = Ikm([ikbs])
    await msg.reply_text(t_[lang]("**▎选择默认解析模式**"), reply_markup=reply_markup)


@Client.on_callback_query(filters.regex(r"^mode"))
async def selected_mode(_: Client, cq: CallbackQuery) -> None:
    if not cq.data:
        return

    cqdata = CQData.parse(cq.data)
    if cq.from_user.id != cqdata.uid:
        async with get_session() as session:
            lang = await AccountService(session, cq.from_user.id).get_lang()
        await cq.answer(t_[lang]("这不是你的操作"), show_alert=True)
        return

    selected = cast(DefaultMode, cqdata.value)
    async with get_session() as session:
        account = AccountService(session, cq.from_user.id)
        current = await account.patch_config(default_mode=selected)

    await cq.message.edit(t_[current.lang](f"**▎已切换为: {MODE_MAP[selected]}**"))


@Client.on_message(filters.command("switch_auto_delete"))
async def switch_auto_delete_url(_: Client, msg: Message) -> None:
    if not msg.from_user:
        return

    async with get_session() as session:
        account = AccountService(session, msg.from_user.id)
        config = await account.get_config()
        current = await account.patch_config(auto_delete_url=not config.auto_delete_url)
    _t = t_[current.lang]
    status = _t('启用') if current.config.auto_delete_url else _t('禁用')
    await msg.reply_text((
            f"{_t(f'** ▎已 {status} 自动删除分享链接消息 **')}\n"
            f"{_t('▎**群内使用需要授予 Bot 删除消息权限**') if current.config.auto_delete_url else ''}"
        )
    )


@Client.on_message(filters.command("switch_platform"))
async def switch_platform(_: Client, msg: Message) -> None:
    if not msg.from_user:
        return

    async with get_session() as session:
        current = await AccountService(session, msg.from_user.id).ensure_account()
        lang = current.lang
        user_config = current.config

    ikbs = [
        Ikb(
            p.display_name,
            callback_data=CQData(key="switch_platform", value=p.id, uid=msg.from_user.id).unparse(),
            style=ButtonStyle.DANGER if p.id in user_config.disabled_platforms else ButtonStyle.SUCCESS,
        )
        for p in list(Platform)
    ]
    reply_markup = Ikm([ikbs[i : i + 2] for i in range(0, len(ikbs), 2)])
    await msg.reply_text(t_[lang]("**▎启用 / 禁用 平台解析**"), reply_markup=reply_markup)


@Client.on_callback_query(filters.regex(r"^switch_platform"))
async def switch_platform_callback(_: Client, cq: CallbackQuery) -> None:
    if not cq.data:
        return

    cqdata = CQData.parse(cq.data)
    if cq.from_user.id != cqdata.uid:
        async with get_session() as session:
            lang = await AccountService(session, cq.from_user.id).get_lang()
        await cq.answer(t_[lang]("这不是你的操作"), show_alert=True)
        return

    selected = cqdata.value
    async with get_session() as session:
        account = AccountService(session, cq.from_user.id)
        current = await account.ensure_account()

        disabled_platforms = current.config.disabled_platforms.copy()
        if selected in disabled_platforms:
            disabled_platforms.remove(selected)
        else:
            disabled_platforms.append(selected)
        current = await account.patch_config(disabled_platforms=disabled_platforms)
        user_config = current.config

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


def build_switches_button(current: AccountContext) -> Ikm:
    uid = current.user.telegram_user_id
    config = current.config
    return Ikm(
        [
            [
                Ikb(
                    "内联发送原始 URL 选项",
                    callback_data=CQData(key="switches", value="enable_inline_raw_url", uid=uid).unparse(),
                    style=ButtonStyle.SUCCESS if config.enable_inline_raw_url else ButtonStyle.DANGER,
                )
            ]
        ]
    )


@Client.on_message(filters.command("switches"))
async def switches(_: Client, msg: Message) -> None:
    if not msg.from_user:
        return
    async with get_session() as session:
        current = await AccountService(session, msg.from_user.id).ensure_account()
    reply_markup = build_switches_button(current)
    await msg.reply("**▎功能开关**", reply_markup=reply_markup)


@Client.on_callback_query(filters.regex(r"^switches"))
async def switches_callback(_: Client, cq: CallbackQuery) -> None:
    if not cq.data:
        return

    cqdata = CQData.parse(cq.data)
    if cq.from_user.id != cqdata.uid:
        async with get_session() as session:
            lang = await AccountService(session, cq.from_user.id).get_lang()
        await cq.answer(t_[lang]("这不是你的操作"), show_alert=True)
        return

    selected = cqdata.value
    match selected:
        case "enable_inline_raw_url":
            async with get_session() as session:
                account = AccountService(session, cq.from_user.id)
                config = await account.get_config()
                current = await account.patch_config(enable_inline_raw_url=not config.enable_inline_raw_url)

    await cq.message.edit_reply_markup(reply_markup=build_switches_button(current))
