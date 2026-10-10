import time
from itertools import batched

from easy_ai18n import PreLocaleSelector
from parsehub.types import Platform as PPlatform
from pydantic import AnyUrl
from pyrogram.enums import ButtonStyle
from pyrogram.types import (
    InputRichBlock,
    InputRichBlockButtons,
    InputRichBlockDetails,
    InputRichBlockParagraph,
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
    RichTextUrl,
)

from core import PlatformsConfig, pl_cfg
from core.platform_config import Platform, url_str
from plugins.helpers import _r
from services import CookieAlert, cookie_health
from utils.helpers import mask_secret

GLOBAL = "_"
"""全局默认代理页的 pid"""
HOME = "home"
ADD_PLATFORM = "add"
KINDS = ("p", "d")
MODES = ("direct", "global", "own")

_PLATFORMS = {p.id: p for p in PPlatform}

CHECK_OFF, CHECK_ON = "▢", "▣"
COOKIES = "c"
"""多选时 cookie 列表的 key, 代理列表用 KINDS"""
type Selection = dict[str, set[str]]
"""列表 key -> 已选中的值"""


def cb(*parts: str | int) -> str:
    return "|".join(["adm", *map(str, parts)])


def _button(text: str, callback_data: str, style: ButtonStyle = ButtonStyle.DEFAULT) -> RichMessageButton:
    return RichMessageButton(text=_r(text), callback_data=callback_data, style=style)


def _cell(text: object, **kwargs: object) -> RichBlockTableCell:
    return RichBlockTableCell(text=_r(text), valign="middle", **kwargs)  # type: ignore[arg-type]


def _button_cell(text: str, callback_data: str, style: ButtonStyle = ButtonStyle.DEFAULT) -> RichBlockTableCell:
    return _cell(RichTextButton(_button(text, callback_data, style)), align="right")


def _heading(text: str, size: int = 2) -> InputRichBlockSectionHeading:
    return InputRichBlockSectionHeading(text=_r(text), size=size)


def _italic(text: str) -> InputRichBlockParagraph:
    return InputRichBlockParagraph(text=_r(RichTextItalic(_r(text))))


def _notice(notice: str | None) -> list[InputRichBlock]:
    return [InputRichBlockParagraph(text=_r(RichTextBold(_r(notice))))] if notice else []


def _lines(parts: list[RichText]) -> RichText:
    out: list[object] = []
    for i, part in enumerate(parts):
        if i:
            out.append("\n")
        out.append(part)
    return _r(out)


def platform_name(pid: str) -> str:
    p = _PLATFORMS.get(pid)
    return p.display_name if p else pid


def kind_label(_t: PreLocaleSelector, kind: str) -> str:
    return str(_t("解析代理") if kind == "p" else _t("下载代理"))


def get_proxies(cfg: PlatformsConfig, pid: str, kind: str) -> list[AnyUrl] | None:
    if pid == GLOBAL:
        return cfg.default_parser_proxies if kind == "p" else cfg.default_downloader_proxies
    pc = cfg.get(pid) or Platform()
    return pc.parser_proxies if kind == "p" else pc.downloader_proxies


def list_values(cfg: PlatformsConfig, pid: str, key: str) -> list[str]:
    if key == COOKIES:
        return [c.get_secret_value() for c in (cfg.get(pid) or Platform()).cookies or []]
    return [url_str(u) for u in get_proxies(cfg, pid, key) or []]


def proxy_mode(pc: Platform, kind: str) -> str:
    """直连 = disable_*_proxy; 专用 = 平台代理列表不为 None (空列表时回落到全局); 其余为全局"""
    if pc.disable_parser_proxy if kind == "p" else pc.disable_downloader_proxy:
        return "direct"
    if (pc.parser_proxies if kind == "p" else pc.downloader_proxies) is not None:
        return "own"
    return "global"


def _mode_label(_t: PreLocaleSelector, mode: str) -> str:
    match mode:
        case "direct":
            return str(_t("直连"))
        case "global":
            return str(_t("全局"))
    return str(_t("专用"))


def _route_label(_t: PreLocaleSelector, pid: str, kind: str) -> str:
    pc = pl_cfg.get(pid) or Platform()
    mode = proxy_mode(pc, kind)
    if mode == "direct":
        return str(_t("直连"))
    if own := get_proxies(pl_cfg, pid, kind):
        return f"{_t('专用')}·{len(own)}"
    return str(_t("全局") if get_proxies(pl_cfg, GLOBAL, kind) else _t("直连"))


def _ago(_t: PreLocaleSelector, ts: float) -> str:
    seconds = int(time.time() - ts)
    if seconds < 60:
        return str(_t("刚刚"))
    if seconds < 3600:
        minutes = seconds // 60
        return str(_t(f"{minutes} 分钟前"))
    if seconds < 86400:
        hours = seconds // 3600
        return str(_t(f"{hours} 小时前"))
    days = seconds // 86400
    return str(_t(f"{days} 天前"))


def _cookie_status(_t: PreLocaleSelector, cookie: str) -> str:
    if cookie_health.is_testing(cookie):
        return f"⏳ {_t('测试中')}"
    stat = cookie_health.get(cookie)
    if stat is None:
        return f"— {_t('暂无记录')}"
    if stat.fail_streak:
        count = stat.fail_streak
        return f"⚠️ {_t(f'连续失败 {count} 次')}"
    if stat.last_success_at:
        ago = _ago(_t, stat.last_success_at)
        return f"✅ {_t(f'{ago}成功')}"
    return f"— {_t('暂无记录')}"


def _cookie_status_cell(_t: PreLocaleSelector, pid: str, index: int, cookie: str) -> RichBlockTableCell:
    """详情页状态列: 红=连续失败, 绿=最近成功, 点击弹出该条详情"""
    stat = cookie_health.get(cookie)
    label, style = "—", ButtonStyle.DEFAULT
    if cookie_health.is_testing(cookie):
        label = str(_t("测试中"))
    elif stat and stat.fail_streak:
        count = stat.fail_streak
        label, style = str(_t(f"失败 {count} 次")), ButtonStyle.DANGER
    elif stat and stat.last_success_at:
        label, style = _ago(_t, stat.last_success_at), ButtonStyle.SUCCESS
    return _cell(RichTextButton(_button(label, cb("cdetail", pid, index), style)), align="center")


def cookie_detail_text(_t: PreLocaleSelector, pid: str, index: int) -> str:
    """单条 cookie 详情弹窗, 不超过 callback answer 的 200 字限制"""
    cookies = [c.get_secret_value() for c in (pl_cfg.get(pid) or Platform()).cookies or []]
    if not 0 <= index < len(cookies):
        return str(_t("列表已变化，请刷新后重试"))
    cookie = cookies[index]
    lines = [f"#{index + 1} {mask_secret(cookie, stars=3)}"]
    if cookie_health.is_testing(cookie):
        lines.append(str(_t("测试中")))
    stat = cookie_health.get(cookie)
    if not stat:
        lines.append(str(_t("暂无记录")))
    else:
        if stat.fail_streak:
            count = stat.fail_streak
            lines.append(str(_t(f"连续失败 {count} 次")))
        if stat.last_success_at:
            ago = _ago(_t, stat.last_success_at)
            lines.append(str(_t(f"最近成功：{ago}")))
        if stat.last_failure_at:
            ago = _ago(_t, stat.last_failure_at)
            lines.append(str(_t(f"最近失败：{ago}")))
        if stat.fail_streak and stat.last_error:
            lines.append(stat.last_error)
    text = "\n".join(lines)
    return text if len(text) <= 200 else f"{text[:199]}…"


def _cookie_summary_cell(pid: str, pc: Platform) -> RichBlockTableCell:
    """首页 cookie 列: 条数按钮, 红=有失败, 绿=都成功过, 点击弹出每条状态"""
    if not pc.cookies:
        return _cell("—", align="center")
    stats = [cookie_health.get(c.get_secret_value()) for c in pc.cookies]
    style = ButtonStyle.DEFAULT
    if any(s and s.fail_streak for s in stats):
        style = ButtonStyle.DANGER
    elif all(s and s.last_success_at for s in stats):
        style = ButtonStyle.SUCCESS
    return _cell(RichTextButton(_button(str(len(pc.cookies)), cb("cstat", pid), style)), align="center")


def cookie_status_text(_t: PreLocaleSelector, pid: str) -> str:
    """cookie 状态弹窗文本, 不超过 callback answer 的 200 字限制"""
    pc = pl_cfg.get(pid) or Platform()
    lines = [f"{platform_name(pid)} Cookie"]
    lines += [f"#{i + 1} {_cookie_status(_t, c.get_secret_value())}" for i, c in enumerate(pc.cookies or [])]
    text = "\n".join(lines)
    return text if len(text) <= 200 else f"{text[:199]}…"


def build_page(
    _t: PreLocaleSelector, page: str, notice: str | None = None, selection: Selection | None = None
) -> InputRichMessage:
    selection = selection or {}
    match page:
        case "home":
            return build_home(_t, notice)
        case "add":
            return build_add_platform(_t)
        case "_":
            return build_global(_t, notice, selection)
    return build_platform(_t, page, notice, selection)


def build_home(_t: PreLocaleSelector, notice: str | None = None) -> InputRichMessage:
    blocks: list[InputRichBlock] = [_heading(f"🌐 {_t('平台配置')}")]
    blocks.append(_italic(_t("修改后立即生效，无需重启。")))

    if pl_cfg.platforms:
        header = [
            _cell(RichTextBold(_r(str(x))), is_header=True, align="center")
            for x in (_t("平台"), _t("解析"), _t("下载"), "Cookie")
        ]
        rows = [[*header, _cell("", is_header=True, align="center")]]
        rows.extend(
            [
                _cell(platform_name(pid), align="center"),
                _cell(_route_label(_t, pid, "p"), align="center"),
                _cell(_route_label(_t, pid, "d"), align="center"),
                _cookie_summary_cell(pid, pc),
                _button_cell(_t("管理"), cb("open", pid)),
            ]
            for pid, pc in pl_cfg.platforms.items()
        )
        blocks.append(InputRichBlockTable(cells=rows, is_bordered=False, is_compact=True))
    else:
        blocks.append(_italic(_t("还没有单独配置的平台，全部使用全局默认代理。")))

    global_rows = []
    for kind in KINDS:
        urls = get_proxies(pl_cfg, GLOBAL, kind)
        value = _lines([RichTextCode(_r(url_str(u))) for u in urls]) if urls else RichTextItalic(_r(_t("未设置")))
        global_rows.append([_cell(RichTextBold(_r(kind_label(_t, kind)))), _cell(value)])
    blocks.append(
        InputRichBlockDetails(
            summary=_r(RichTextBold(_r(_t("全局默认代理")))),
            blocks=[
                InputRichBlockTable(cells=global_rows, is_bordered=False, is_compact=True),
                InputRichBlockButtons(buttons=[_button(_t("编辑"), cb("open", GLOBAL))]),
            ],
        )
    )
    blocks += _notice(notice)
    blocks += [
        InputRichBlockButtons(
            buttons=[
                _button(_t("导出配置"), cb("export")),
                _button(_t("重载配置"), cb("reload")),
                _button(_t("导入配置"), cb("import")),
            ],
            align="center",
        ),
        InputRichBlockButtons(
            buttons=[
                _button(f"＋ {_t('添加平台')}", cb("open", ADD_PLATFORM), ButtonStyle.SUCCESS),
                _button(_t("完成"), cb("done"), ButtonStyle.PRIMARY),
            ],
            align="center",
        ),
    ]
    return InputRichMessage(blocks=blocks)


def _check_cell(checked: bool, callback_data: str) -> RichBlockTableCell:
    return _cell(
        RichTextButton(
            _button(
                CHECK_ON if checked else CHECK_OFF,
                callback_data,
                ButtonStyle.PRIMARY if checked else ButtonStyle.DEFAULT,
            )
        )
    )


def _select_all_header(
    _t: PreLocaleSelector, pid: str, key: str, values: list[str], selected: set[str], labels: list[str], blanks: int
) -> list[RichBlockTableCell]:
    """表头: 第一格是全选按钮, 后面是列名, 按钮列留空"""
    label = _t("反选") if selected >= set(values) else _t("全选")
    return [
        _cell(RichTextButton(_button(label, cb("selall", pid, key))), is_header=True),
        *(_cell(RichTextBold(_r(x)), is_header=True) for x in labels),
        *(_cell("", is_header=True) for _ in range(blanks)),
    ]


def _bulk_buttons(
    _t: PreLocaleSelector,
    pid: str,
    key: str,
    values: list[str],
    selected: set[str],
    add: RichMessageButton,
    test_action: str | None = None,
) -> InputRichBlockButtons:
    buttons = []
    if values and selected:
        count = len(selected & set(values))
        if test_action:
            buttons.append(_button(_t(f"测试所选 ({count})"), cb(test_action, pid)))
        buttons.append(_button(_t(f"删除所选 ({count})"), cb("delsel", pid, key), ButtonStyle.DANGER))
    buttons.append(add)
    return InputRichBlockButtons(buttons=buttons)


def _proxy_list(
    _t: PreLocaleSelector, pid: str, kind: str, empty_hint: str, selection: Selection
) -> list[InputRichBlock]:
    blocks: list[InputRichBlock] = []
    values = list_values(pl_cfg, pid, kind)
    selected = selection.get(kind, set()) & set(values)
    if values:
        blocks.append(
            InputRichBlockTable(
                cells=[
                    _select_all_header(_t, pid, kind, values, selected, [_t("代理")], 1),
                    *[
                        [
                            _check_cell(u in selected, cb("sel", pid, kind, i)),
                            _cell(RichTextCode(_r(u))),
                            _button_cell(_t("测试"), cb("test", pid, kind, i)),
                        ]
                        for i, u in enumerate(values)
                    ],
                ],
                is_bordered=False,
                is_compact=True,
            )
        )
    else:
        blocks.append(_italic(empty_hint))
    blocks.append(
        _bulk_buttons(
            _t, pid, kind, values, selected, _button(f"＋ {_t('添加代理')}", cb("addp", pid, kind), ButtonStyle.SUCCESS)
        )
    )
    return blocks


def build_global(_t: PreLocaleSelector, notice: str | None, selection: Selection) -> InputRichMessage:
    blocks: list[InputRichBlock] = [_heading(f"🌐 {_t('全局默认代理')}")]
    blocks.append(_italic(_t("没有单独配置代理的平台使用这里的代理，多条时每次随机选一条。")))
    for kind in KINDS:
        blocks.append(_heading(kind_label(_t, kind), 4))
        blocks += _proxy_list(_t, GLOBAL, kind, _t("未设置，使用全局代理的平台会直连"), selection)
    blocks += _notice(notice)
    blocks += [
        InputRichBlockButtons(
            buttons=[_button(f"‹ {_t('返回')}", cb("open", HOME))],
            align="center",
        ),
    ]
    return InputRichMessage(blocks=blocks)


def build_platform(_t: PreLocaleSelector, pid: str, notice: str | None, selection: Selection) -> InputRichMessage:
    pc = pl_cfg.get(pid) or Platform()
    blocks: list[InputRichBlock] = [_heading(f"⚙️ {platform_name(pid)}")]

    for kind in KINDS:
        mode = proxy_mode(pc, kind)
        blocks.append(_heading(kind_label(_t, kind), 4))
        blocks.append(
            InputRichBlockButtons(
                buttons=[
                    _button(
                        f"{'● ' if mode == m else ''}{_mode_label(_t, m)}",
                        cb("mode", pid, kind, m),
                        ButtonStyle.PRIMARY if mode == m else ButtonStyle.DEFAULT,
                    )
                    for m in MODES
                ]
            )
        )
        if mode == "own":
            blocks += _proxy_list(_t, pid, kind, _t("专用代理池为空，会回落到全局默认代理"), selection)
        elif mode == "global":
            if urls := get_proxies(pl_cfg, GLOBAL, kind):
                count = len(urls)
                blocks.append(_italic(_t(f"使用全局默认代理（{count} 条）")))
            else:
                blocks.append(_italic(_t("全局默认代理未设置，实际直连")))
        else:
            blocks.append(_italic(_t("不走代理")))

    blocks.append(_heading("Cookie", 4))
    cookies = list_values(pl_cfg, pid, COOKIES)
    selected = selection.get(COOKIES, set()) & set(cookies)
    if cookies:
        blocks.append(
            InputRichBlockTable(
                cells=[
                    _select_all_header(_t, pid, COOKIES, cookies, selected, ["Cookie", _t("状态")], 2),
                    *[
                        [
                            _check_cell(c in selected, cb("sel", pid, COOKIES, i)),
                            _cell(mask_secret(c, stars=3)),
                            _cookie_status_cell(_t, pid, i, c),
                            _button_cell(_t("测试"), cb("testc", pid, i)),
                            _button_cell(_t("替换"), cb("repc", pid, i)),
                        ]
                        for i, c in enumerate(cookies)
                    ],
                ],
                is_bordered=False,
                is_compact=True,
            )
        )
    else:
        blocks.append(_italic(_t("未配置 Cookie")))

    blocks.append(
        _bulk_buttons(
            _t,
            pid,
            COOKIES,
            cookies,
            selected,
            _button(f"＋ {_t('添加 Cookie')}", cb("addc", pid), ButtonStyle.SUCCESS),
            test_action="testsel",
        )
    )

    blocks += _notice(notice)
    bottom = [_button(f"‹ {_t('返回')}", cb("open", HOME))]
    if pid in pl_cfg.platforms:
        bottom.append(_button(_t("删除该平台配置"), cb("delpf", pid), ButtonStyle.DANGER))
    blocks += [InputRichBlockButtons(buttons=bottom, align="center")]
    return InputRichMessage(blocks=blocks)


def build_add_platform(_t: PreLocaleSelector) -> InputRichMessage:
    blocks: list[InputRichBlock] = [
        _heading(f"＋ {_t('添加平台')}"),
        _italic(_t("选择要单独配置的平台")),
    ]
    unconfigured = [p for p in PPlatform if p.id not in pl_cfg.platforms]
    blocks.extend(
        InputRichBlockButtons(buttons=[_button(p.display_name, cb("open", p.id)) for p in row])
        for row in batched(unconfigured, 3)
    )
    blocks += [
        InputRichBlockButtons(buttons=[_button(f"‹ {_t('返回')}", cb("open", HOME))], align="center"),
    ]
    return InputRichMessage(blocks=blocks)


def build_cookie_alert(_t: PreLocaleSelector, alert: CookieAlert) -> InputRichMessage:
    name = platform_name(alert.platform_id)
    count = alert.stat.fail_streak
    rows = [
        [_cell(RichTextBold(_r(_t("平台")))), _cell(name)],
        [_cell(RichTextBold(_r("Cookie"))), _cell(mask_secret(alert.cookie))],
        [_cell(RichTextBold(_r(_t("连续失败")))), _cell(_t(f"{count} 次"))],
        [_cell(RichTextBold(_r(_t("错误")))), _cell(RichTextCode(_r((alert.stat.last_error or "")[:300])))],
        [_cell(RichTextBold(_r(_t("链接")))), _cell(RichTextUrl(_r(alert.url), alert.url))],
    ]
    return InputRichMessage(
        blocks=[
            _heading(f"⚠️ {_t(f'{name} 的 Cookie 可能已失效')}"),
            InputRichBlockTable(cells=rows, is_bordered=False, is_compact=True),
            _italic(_t("带这条 Cookie 的解析连续失败。更新后可以用原链接重试验证。")),
            InputRichBlockButtons(
                buttons=[
                    _button(_t("管理 Cookie"), cb("open", alert.platform_id), ButtonStyle.PRIMARY),
                    _button(_t("用原链接重试"), cb("retry", alert.platform_id)),
                ]
            ),
        ]
    )
