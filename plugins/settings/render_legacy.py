from itertools import batched

from easy_ai18n import PreLocaleSelector
from parsehub.types import Platform
from pyrogram.enums import ButtonStyle
from pyrogram.types import InlineKeyboardButton as Ikb
from pyrogram.types import InlineKeyboardMarkup as Ikm

from plugins.settings.models import BOOL_SWITCHES, CfgAction, CfgCQData, CfgPage, SettingsViewModel
from plugins.settings.target import cfg_callback_data
from repo.settings import ParseMode
from services import ChannelSettingsTarget


def build_cfg_markup(_t: PreLocaleSelector, vm: SettingsViewModel, page: CfgPage = CfgPage.MAIN) -> Ikm:
    if vm.target is None:
        return build_cfg_target_markup(vm)
    if page == CfgPage.PLATFORM:
        return build_cfg_platform_markup(_t, vm)
    return build_cfg_main_markup(_t, vm)


def build_cfg_target_markup(vm: SettingsViewModel) -> Ikm:
    return Ikm(
        [
            [
                Ikb(
                    option.label,
                    callback_data=CfgCQData(
                        action=CfgAction.SELECT_TARGET,
                        value=CfgPage.MAIN.value,
                        scope=option.scope,
                        channel_id=option.target.telegram_chat_id
                        if isinstance(option.target, ChannelSettingsTarget)
                        else None,
                    ).unparse(),
                )
            ]
            for option in vm.target_options
        ]
    )


def build_cfg_main_markup(_t: PreLocaleSelector, vm: SettingsViewModel) -> Ikm:
    rows: list[list[Ikb]] = []
    mode_map = {
        ParseMode.PREVIEW: "/jx",
        ParseMode.RAW: "/raw",
        ParseMode.ZIP: "/zip",
    }
    if "default_mode" in vm.allowed_fields:
        rows.append([Ikb(_t("默认解析模式"), callback_data="placeholder", style=ButtonStyle.PRIMARY)])
        rows.append(
            [
                Ikb(
                    label,
                    callback_data=cfg_callback_data(CfgAction.SET_MODE, value.value, vm.target),
                    style=ButtonStyle.PRIMARY if value == vm.config.default_mode else ButtonStyle.DEFAULT,
                )
                for value in ParseMode
                for label in [mode_map[value]]
            ]
        )

    if "disabled_platforms" in vm.allowed_fields:
        rows.append(
            [
                Ikb(
                    cfg_page_label(_t, CfgPage.PLATFORM),
                    callback_data=cfg_callback_data(CfgAction.OPEN_PAGE, CfgPage.PLATFORM.value, vm.target),
                )
            ]
        )

    switches = [switch for switch in BOOL_SWITCHES if switch.field in vm.allowed_fields]
    buttons = [
        Ikb(
            switch.label[_t.locale],
            callback_data=cfg_callback_data(CfgAction.TOGGLE_BOOL, switch.code, vm.target),
            style=reply_bool_style(switch.get_value(vm.config)),
        )
        for switch in switches
    ]
    rows.extend([list(row) for row in batched(buttons, 2)])
    rows.append([build_done_button(_t, vm)])

    return Ikm(rows)


def build_cfg_platform_markup(_t: PreLocaleSelector, vm: SettingsViewModel) -> Ikm:
    ikbs = [
        Ikb(
            p.display_name,
            callback_data=cfg_callback_data(CfgAction.TOGGLE_PLATFORM, p.id, vm.target),
            style=ButtonStyle.DANGER if p.id in vm.config.disabled_platforms else ButtonStyle.SUCCESS,
        )
        for p in list(Platform)
    ]
    rows = [list(row) for row in batched(ikbs, 2)]
    rows.append(
        [
            Ikb(_t("返回"), callback_data=cfg_callback_data(CfgAction.OPEN_PAGE, CfgPage.MAIN.value, vm.target)),
            build_done_button(_t, vm),
        ]
    )
    return Ikm(rows)


def cfg_page_label(_t: PreLocaleSelector, page: CfgPage) -> str:
    match page:
        case CfgPage.PLATFORM:
            label = _t("平台管理")
        case CfgPage.MAIN:
            label = ""
    return str(label)


def build_done_button(_t: PreLocaleSelector, vm: SettingsViewModel) -> Ikb:
    return Ikb(
        _t("完成"),
        callback_data=cfg_callback_data(CfgAction.DONE, CfgPage.MAIN.value, vm.target),
        style=ButtonStyle.PRIMARY,
    )


def reply_bool_style(v: bool) -> ButtonStyle:
    return ButtonStyle.SUCCESS if v else ButtonStyle.DANGER
