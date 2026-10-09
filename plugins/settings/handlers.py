from easy_ai18n import PreLocaleSelector
from pyrogram import Client, filters
from pyrogram.enums import ChatType
from pyrogram.errors import RPCError
from pyrogram.types import CallbackQuery, InputRichBlockSectionHeading, InputRichMessage, Message

from db import get_session
from i18n import t_
from plugins.helpers import _r, format_label
from plugins.settings.models import BOOL_SWITCH_MAP, CfgAction, CfgCQData, CfgPage, SettingsViewModel
from plugins.settings.render import build_cfg_rich_message, build_cfg_title
from plugins.settings.render_legacy import build_cfg_markup
from plugins.settings.target import (
    build_cfg_target_options,
    ensure_cfg_field,
    ensure_cfg_permission,
    get_allowed_fields,
    resolve_channel_target,
    restore_cfg_target,
)
from repo.settings import ParseMode, SettingsConfig
from services import SettingsService, UserService
from services.settings import (
    AnySettingsTarget,
    ChannelSettingsTarget,
    ForumTopicMemberSettingsTarget,
    ForumTopicSettingsTarget,
    GroupMemberSettingsTarget,
    GroupSettingsTarget,
    UserSettingsTarget,
)


@Client.on_message(filters.command("cfg"))
async def cfg(cli: Client, msg: Message) -> None:
    await cfg_command(cli, msg, legacy=False)


@Client.on_message(filters.command("ocfg"))
async def ocfg(cli: Client, msg: Message) -> None:
    await cfg_command(cli, msg, legacy=True)


async def cfg_command(cli: Client, msg: Message, *, legacy: bool) -> None:
    if not msg.from_user:
        return

    async with get_session() as session:
        lang = await UserService(session).get_lang(msg.from_user.id)
        _t = t_[lang]

    channel_ref = msg.command[1] if msg.command and msg.command[1:] else None
    if channel_ref:
        target = await resolve_channel_target(cli, msg, _t, channel_ref)
        if not target:
            return
        async with get_session() as session:
            vm = await build_cfg_vm(SettingsService(session), _t, target, "频道配置")
        await reply_cfg_panel(msg, _t, vm, legacy=legacy)
        return

    options = await build_cfg_target_options(cli, msg, _t)
    if not options:
        return

    if len(options) == 1:
        option = options[0]
        async with get_session() as session:
            vm = await build_cfg_vm(SettingsService(session), _t, option.target, option.label)
        await reply_cfg_panel(msg, _t, vm, legacy=legacy)
        return

    vm = SettingsViewModel(
        config=SettingsConfig(),
        target=None,
        allowed_fields=frozenset(),
        target_label=None,
        target_options=tuple(options),
    )
    await reply_cfg_panel(msg, _t, vm, legacy=legacy)


async def reply_cfg_panel(msg: Message, _t: PreLocaleSelector, vm: SettingsViewModel, *, legacy: bool) -> None:
    if legacy:
        text = _t("选择配置目标") if vm.target is None else build_cfg_title(_t, vm.target_label)
        await msg.reply(format_label(text), reply_markup=build_cfg_markup(_t, vm))
        return
    await msg.reply_rich(rich_message=build_cfg_rich_message(_t, vm))


@Client.on_callback_query(filters.regex(r"^cfg"))
async def cfg_callback(cli: Client, cq: CallbackQuery) -> None:
    if not cq.data or not cq.message:
        return

    data = CfgCQData.parse(cq.data)
    legacy = cq.message.rich_message is None
    async with get_session() as session:
        lang = await UserService(session).get_lang(cq.from_user.id)
        _t = t_[lang]
    if data.action == CfgAction.DONE:
        await finish_cfg_panel(cli, cq, _t, data)
        return

    target = restore_cfg_target(cq, data)
    if not target:
        await cq.answer(_t("无法识别配置目标"), show_alert=True)
        return

    if not await ensure_cfg_permission(cli, cq, _t, target):
        return

    async with get_session() as session:
        settings = SettingsService(session)
        match data.action:
            case CfgAction.SELECT_TARGET:
                pass
            case CfgAction.SET_MODE:
                selected = ParseMode(data.value)
                if not await ensure_cfg_field(cq, _t, target, "default_mode"):
                    return
                if (await settings.get_config(target)).default_mode == selected:
                    await cq.answer()
                    return
                await settings.patch_config(target, default_mode=selected)
            case CfgAction.TOGGLE_BOOL:
                switch = BOOL_SWITCH_MAP.get(data.value)
                if not switch:
                    await cq.answer(_t("未知配置项"), show_alert=True)
                    return
                if not await ensure_cfg_field(cq, _t, target, switch.field):
                    return
                config = await settings.get_config(target)
                await switch.patch(settings, target, not switch.get_value(config))
            case CfgAction.TOGGLE_PLATFORM:
                if not await ensure_cfg_field(cq, _t, target, "disabled_platforms"):
                    return
                config = await settings.get_config(target)
                disabled_platforms = config.disabled_platforms.copy()
                if data.value in disabled_platforms:
                    disabled_platforms.remove(data.value)
                else:
                    disabled_platforms.append(data.value)
                await settings.patch_config(target, disabled_platforms=disabled_platforms)
            case CfgAction.OPEN_PAGE:
                pass
            case CfgAction.DONE:
                pass
            case CfgAction.EXPAND:
                pass

        label = get_cfg_target_label(_t, target)
        vm = await build_cfg_vm(settings, _t, target, label)

    expanded = data.expanded
    if data.action == CfgAction.EXPAND:
        expanded = None if data.expanded == data.value else data.value
    focus = data.value if data.action in (CfgAction.TOGGLE_BOOL, CfgAction.EXPAND) else None
    page = (
        CfgPage.PLATFORM
        if data.action == CfgAction.TOGGLE_PLATFORM or data.value == CfgPage.PLATFORM.value
        else CfgPage.MAIN
    )
    if legacy:
        await cq.message.edit(
            format_label(build_cfg_title(_t, vm.target_label, page)),
            reply_markup=build_cfg_markup(_t, vm, page),
        )
    else:
        await cq.message.edit_text(rich_message=build_cfg_rich_message(_t, vm, page, expanded=expanded, focus=focus))
    await cq.answer()


async def finish_cfg_panel(cli: Client, cq: CallbackQuery, _t: PreLocaleSelector, data: CfgCQData) -> None:
    if not cq.message:
        return

    legacy = cq.message.rich_message is None
    target = restore_cfg_target(cq, data)
    if not target:
        await cq.answer(_t("无法识别配置目标"), show_alert=True)
        return

    label = get_cfg_target_label(_t, target)

    if await can_delete_cfg_messages(cli, cq):
        await delete_cfg_messages(cq.message)
        await cq.answer()
        return

    if legacy:
        await cq.message.edit(format_label(build_cfg_title(_t, label, suffix=_t("完成"))), reply_markup=None)
    else:
        await cq.message.edit_text(
            rich_message=InputRichMessage(
                blocks=[
                    InputRichBlockSectionHeading(
                        text=_r(f"⚙️ {build_cfg_title(_t, label, suffix=_t('完成'))}"),
                        size=2,
                    )
                ]
            )
        )
    await cq.answer()


async def can_delete_cfg_messages(cli: Client, cq: CallbackQuery) -> bool:
    msg = cq.message
    if not msg or not msg.chat:
        return False
    if msg.chat.type == ChatType.PRIVATE:
        return True
    chat_id = msg.chat.id
    if chat_id is None:
        return False
    try:
        member = await cli.get_chat_member(chat_id, "me")
    except Exception:
        return False

    privileges = member.privileges
    return bool(privileges and privileges.can_delete_messages)


async def delete_cfg_messages(menu_msg: Message) -> None:
    messages = [menu_msg]
    if menu_msg.reply_to_message:
        messages.append(menu_msg.reply_to_message)

    for msg in messages:
        try:
            await msg.delete()
        except RPCError:
            pass


def get_cfg_target_label(_t: PreLocaleSelector, target: AnySettingsTarget) -> str:
    match target:
        case UserSettingsTarget():
            label = _t("个人配置")
        case GroupSettingsTarget():
            label = _t("群组配置")
        case GroupMemberSettingsTarget():
            label = _t("群内个人配置")
        case ForumTopicSettingsTarget():
            label = _t("话题配置")
        case ForumTopicMemberSettingsTarget():
            label = _t("话题内个人配置")
        case ChannelSettingsTarget():
            label = _t("频道配置")
    return str(label)


async def build_cfg_vm(
    settings: SettingsService, _t: PreLocaleSelector, target: AnySettingsTarget, target_label: str
) -> SettingsViewModel:
    return SettingsViewModel(
        config=await settings.get_config(target),
        target=target,
        allowed_fields=get_allowed_fields(target.scope),
        target_label=_t(target_label),
    )
