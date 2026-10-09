from itertools import batched

from easy_ai18n import PreLocaleSelector
from parsehub.types import Platform
from pyrogram.enums import ButtonStyle
from pyrogram.types import (
    InputMediaPhoto,
    InputRichBlock,
    InputRichBlockButtons,
    InputRichBlockDetails,
    InputRichBlockDivider,
    InputRichBlockList,
    InputRichBlockListItem,
    InputRichBlockParagraph,
    InputRichBlockPhoto,
    InputRichBlockPreformatted,
    InputRichBlockSectionHeading,
    InputRichBlockTable,
    InputRichMessage,
    RichBlockTableCell,
    RichMessageButton,
    RichText,
    RichTextBold,
    RichTextButton,
    RichTextCode,
    RichTextItalic,
)

from plugins.helpers import COMMANDS, _r
from plugins.settings.models import (
    BOOL_SWITCH_MAP,
    EXPAND_MODE,
    EXPAND_PLATFORM,
    MODE_DESC,
    PLATFORM_DESC,
    SWITCH_GROUPS,
    CfgAction,
    CfgPage,
    SettingsViewModel,
)
from plugins.settings.target import cfg_callback_data
from repo.settings import ParseMode


def _button(text: str, callback_data: str, style: ButtonStyle = ButtonStyle.DEFAULT) -> RichMessageButton:
    return RichMessageButton(text=_r(text), callback_data=callback_data, style=style)


def build_cfg_rich_message(
    _t: PreLocaleSelector,
    vm: SettingsViewModel,
    page: CfgPage = CfgPage.MAIN,
    *,
    expanded: str | None = None,
    focus: str | None = None,
) -> InputRichMessage:
    if vm.target is None:
        blocks: list[InputRichBlock] = [InputRichBlockSectionHeading(text=_r(f"⚙️ {_t('选择配置目标')}"), size=2)]
        blocks.extend(
            InputRichBlockButtons(
                buttons=[
                    _button(
                        option.label,
                        cfg_callback_data(CfgAction.SELECT_TARGET, CfgPage.MAIN.value, option.target),
                    )
                ]
            )
            for option in vm.target_options
        )
        return InputRichMessage(blocks=blocks)

    title = _r(f"⚙️ {build_cfg_title(_t, vm.target_label, page)}")
    if page == CfgPage.PLATFORM:
        platforms = list(Platform)
        disabled_platforms = set(vm.config.disabled_platforms)
        cells = [
            cell
            for platform in platforms
            for cell in (
                RichBlockTableCell(text=_r(platform.display_name), valign="middle"),
                RichBlockTableCell(
                    text=RichTextButton(
                        _button(
                            _t("关") if platform.id in disabled_platforms else _t("开"),
                            cfg_callback_data(
                                CfgAction.TOGGLE_PLATFORM,
                                platform.id,
                                vm.target,
                                expanded=expanded,
                            ),
                            ButtonStyle.DANGER if platform.id in disabled_platforms else ButtonStyle.SUCCESS,
                        )
                    ),
                    align="right",
                    valign="middle",
                ),
            )
        ]
        rows = [list(row) for row in batched(cells, 4)]
        if rows and len(rows[-1]) < 4:
            rows[-1].extend(RichBlockTableCell(text=_r("")) for _ in range(4 - len(rows[-1])))
        return InputRichMessage(
            blocks=[
                InputRichBlockSectionHeading(text=title, size=2),
                InputRichBlockParagraph(text=_r(RichTextItalic(_r(PLATFORM_DESC[_t.locale])))),
                InputRichBlockTable(cells=rows, is_bordered=False),
                InputRichBlockDivider(),
                InputRichBlockButtons(
                    buttons=[
                        _button(
                            f"‹ {_t('返回')}",
                            cfg_callback_data(
                                CfgAction.OPEN_PAGE,
                                CfgPage.MAIN.value,
                                vm.target,
                                expanded=expanded,
                            ),
                        ),
                        _button(
                            _t("完成"),
                            cfg_callback_data(
                                CfgAction.DONE,
                                CfgPage.MAIN.value,
                                vm.target,
                                expanded=expanded,
                            ),
                            ButtonStyle.PRIMARY,
                        ),
                    ],
                    align="center",
                ),
            ]
        )

    blocks = [
        InputRichBlockSectionHeading(text=title, size=2),
    ]
    basic_items = []
    if "default_mode" in vm.allowed_fields:
        basic_items.append((EXPAND_MODE, _t("默认解析模式")))
    if "disabled_platforms" in vm.allowed_fields:
        basic_items.append((EXPAND_PLATFORM, _t("平台管理")))
    if basic_items:
        blocks.extend(_split_table(_t, vm, basic_items, expanded))

    for group in SWITCH_GROUPS:
        items = [
            (code, BOOL_SWITCH_MAP[code].label[_t.locale])
            for code in group.codes
            if BOOL_SWITCH_MAP[code].field in vm.allowed_fields
        ]
        if not items:
            continue
        item_codes = {code for code, _ in items}
        blocks.append(
            InputRichBlockDetails(
                summary=_r(RichTextBold(_r(group.label[_t.locale]))),
                blocks=_split_table(_t, vm, items, expanded),
                is_open=expanded in item_codes or focus in item_codes,
            )
        )

    blocks.append(
        InputRichBlockButtons(
            buttons=[
                _button(
                    _t("完成"),
                    cfg_callback_data(CfgAction.DONE, CfgPage.MAIN.value, vm.target),
                    ButtonStyle.PRIMARY,
                )
            ],
            align="center",
        )
    )
    return InputRichMessage(blocks=blocks)


def _split_table(
    _t: PreLocaleSelector,
    vm: SettingsViewModel,
    items: list[tuple[str, str]],
    expanded: str | None,
) -> list[InputRichBlock]:
    blocks: list[InputRichBlock] = []
    rows: list[list[RichBlockTableCell]] = []

    def flush() -> None:
        if rows:
            blocks.append(InputRichBlockTable(cells=rows.copy(), is_bordered=False))
            rows.clear()

    for code, label in items:
        is_expanded = expanded == code
        rows.append(
            [
                RichBlockTableCell(
                    text=RichTextButton(
                        _button(
                            f"{label} {'▴' if is_expanded else '▾'}",
                            cfg_callback_data(CfgAction.EXPAND, code, vm.target, expanded=expanded),
                        )
                    ),
                    valign="middle",
                ),
                RichBlockTableCell(
                    text=_right_cell(_t, vm, code, expanded),
                    align="right",
                    valign="middle",
                ),
            ]
        )
        if is_expanded:
            flush()
            blocks.extend(_expanded_blocks(_t, code))
    flush()
    return blocks


def _right_cell(_t: PreLocaleSelector, vm: SettingsViewModel, code: str, expanded: str | None) -> RichText:
    if code == EXPAND_MODE:
        mode_labels = {
            ParseMode.PREVIEW: "/jx",
            ParseMode.RAW: "/raw",
            ParseMode.ZIP: "/zip",
        }
        content: list[RichText] = []
        for mode, label in mode_labels.items():
            if content:
                content.append(_r(" "))
            content.append(
                RichTextButton(
                    _button(
                        label,
                        cfg_callback_data(CfgAction.SET_MODE, mode.value, vm.target, expanded=expanded),
                        ButtonStyle.PRIMARY if vm.config.default_mode == mode else ButtonStyle.DEFAULT,
                    )
                )
            )
        return _r(content)
    if code == EXPAND_PLATFORM:
        platforms = list(Platform)
        disabled_platforms = set(vm.config.disabled_platforms)
        enabled_count = sum(platform.id not in disabled_platforms for platform in platforms)
        return RichTextButton(
            _button(
                f"{_t('已启用')} {enabled_count}/{len(platforms)} ›",
                cfg_callback_data(CfgAction.OPEN_PAGE, CfgPage.PLATFORM.value, vm.target, expanded=expanded),
            )
        )

    switch = BOOL_SWITCH_MAP[code]
    enabled = switch.get_value(vm.config)
    return RichTextButton(
        _button(
            _t("开") if enabled else _t("关"),
            cfg_callback_data(CfgAction.TOGGLE_BOOL, code, vm.target, expanded=expanded),
            reply_bool_style(enabled),
        )
    )


def _inline_code(text: str) -> RichText:
    parts = text.split("`")
    return _r([RichTextCode(_r(part)) if i % 2 else part for i, part in enumerate(parts) if part])


def _expanded_blocks(_t: PreLocaleSelector, code: str) -> list[InputRichBlock]:
    if code == EXPAND_MODE:
        return [
            InputRichBlockParagraph(text=_r(MODE_DESC[_t.locale])),
            InputRichBlockList(
                items=[
                    InputRichBlockListItem(
                        blocks=[
                            InputRichBlockParagraph(
                                text=_r([RichTextCode(_r(f"/{command}")), " ", COMMANDS[command][_t.locale]])
                            )
                        ]
                    )
                    for command in ("jx", "raw", "zip")
                ]
            ),
        ]
    if code == EXPAND_PLATFORM:
        return [InputRichBlockParagraph(text=_r(PLATFORM_DESC[_t.locale]))]
    switch = BOOL_SWITCH_MAP[code]
    blocks: list[InputRichBlock] = [InputRichBlockParagraph(text=_inline_code(switch.desc[_t.locale]))]
    if switch.example is not None:
        blocks.append(InputRichBlockPreformatted(text=_r(switch.example[_t.locale])))
    if switch.image is not None:
        blocks.append(InputRichBlockPhoto(photo=InputMediaPhoto(str(switch.image))))
    return blocks


def cfg_page_label(_t: PreLocaleSelector, page: CfgPage) -> str:
    match page:
        case CfgPage.PLATFORM:
            label = _t("平台管理")
        case CfgPage.MAIN:
            label = ""
    return str(label)


def build_cfg_title(
    _t: PreLocaleSelector,
    target_label: str | None,
    page: CfgPage = CfgPage.MAIN,
    *,
    suffix: str | None = None,
) -> str:
    parts = [_t("配置面板")]
    if target_label:
        parts.append(target_label)
    if page_label := cfg_page_label(_t, page):
        parts.append(page_label)
    if suffix:
        parts.append(suffix)
    return " - ".join(parts)


def reply_bool_style(value: bool) -> ButtonStyle:
    return ButtonStyle.SUCCESS if value else ButtonStyle.DANGER
