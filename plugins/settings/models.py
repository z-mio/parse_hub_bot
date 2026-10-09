from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Self

from easy_ai18n import LocaleContent

from i18n import t_
from repo.settings import SettingsConfig
from services import SettingsService
from services.settings import AnySettingsTarget

ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets"


class CfgAction(StrEnum):
    SELECT_TARGET = "t"
    SET_MODE = "m"
    TOGGLE_BOOL = "b"
    TOGGLE_PLATFORM = "p"
    OPEN_PAGE = "o"
    DONE = "d"
    EXPAND = "x"


class CfgScopeCode(StrEnum):
    USER = "u"
    GROUP = "g"
    GROUP_MEMBER = "gm"
    FORUM_TOPIC = "ft"
    FORUM_TOPIC_MEMBER = "ftm"
    CHANNEL = "c"


class CfgPage(StrEnum):
    MAIN = "main"
    PLATFORM = "p"


@dataclass(frozen=True, slots=True)
class CfgCQData:
    action: CfgAction
    value: str
    scope: CfgScopeCode | None = None
    channel_id: int | None = None
    user_id: int | None = None
    expanded: str | None = None

    @classmethod
    def parse(cls, data: str | bytes) -> Self:
        parts = str(data).split("|")
        _, action, value, *rest = parts
        scope = CfgScopeCode(rest[0]) if rest else None
        channel_id = int(rest[1]) if len(rest) > 1 and rest[1] else None
        user_id = int(rest[2]) if len(rest) > 2 and rest[2] else None
        expanded = rest[3] or None if len(rest) > 3 else None
        return cls(
            action=CfgAction(action),
            value=value,
            scope=scope,
            channel_id=channel_id,
            user_id=user_id,
            expanded=expanded,
        )

    def unparse(self) -> str:
        parts = ["cfg", self.action.value, self.value]
        if not self.scope:
            return "|".join(parts)
        tail = [
            self.scope.value,
            str(self.channel_id) if self.channel_id is not None else "",
            str(self.user_id) if self.user_id is not None else "",
            self.expanded or "",
        ]
        while tail and not tail[-1]:
            tail.pop()
        parts.extend(tail)
        return "|".join(parts)


@dataclass(frozen=True, slots=True)
class CfgTargetOption:
    label: str
    scope: CfgScopeCode
    target: AnySettingsTarget


@dataclass(frozen=True, slots=True)
class SettingsViewModel:
    config: SettingsConfig
    target: AnySettingsTarget | None
    allowed_fields: frozenset[str]
    target_label: str | None
    target_options: tuple[CfgTargetOption, ...] = ()


@dataclass(frozen=True, slots=True)
class BoolSwitchDTO:
    field: str
    code: str
    label: LocaleContent
    desc: LocaleContent
    get_value: Callable[[SettingsConfig], bool]
    patch: Callable[[SettingsService, AnySettingsTarget, bool], Awaitable[SettingsConfig]]
    example: LocaleContent | None = None
    image: Path | None = None


@dataclass(frozen=True, slots=True)
class SwitchGroupDTO:
    label: LocaleContent
    codes: tuple[str, ...]


BOOL_SWITCHES = (
    BoolSwitchDTO(
        field="hide_title",
        code="ht",
        label=t_("隐藏标题"),
        desc=t_("解析结果不显示帖子标题。用 Telegraph 或富文本发送的文章不受影响。"),
        get_value=lambda config: config.hide_title,
        patch=lambda settings, target, value: settings.patch_config(target, hide_title=value),
    ),
    BoolSwitchDTO(
        field="hide_desc",
        code="hd",
        label=t_("隐藏简介"),
        desc=t_("解析结果不显示帖子正文简介。用 Telegraph 或富文本发送的文章不受影响。"),
        get_value=lambda config: config.hide_desc,
        patch=lambda settings, target, value: settings.patch_config(target, hide_desc=value),
    ),
    BoolSwitchDTO(
        field="video_cover",
        code="vc",
        label=t_("视频封面"),
        desc=t_("发送视频时使用平台提供的封面图作为视频封面，关闭后不设置封面。"),
        get_value=lambda config: config.video_cover,
        patch=lambda settings, target, value: settings.patch_config(target, video_cover=value),
    ),
    BoolSwitchDTO(
        field="reply_msg",
        code="rm",
        label=t_("回复消息"),
        desc=t_("解析结果以回复原消息的形式发送，关闭后直接发到聊天里。"),
        get_value=lambda config: config.reply_msg,
        patch=lambda settings, target, value: settings.patch_config(target, reply_msg=value),
    ),
    BoolSwitchDTO(
        field="hide_source",
        code="hs",
        label=t_("隐藏底部「Source」"),
        desc=t_("解析结果末尾不再附带「Source」原链接。"),
        get_value=lambda config: config.hide_source,
        patch=lambda settings, target, value: settings.patch_config(target, hide_source=value),
    ),
    BoolSwitchDTO(
        field="auto_delete_url",
        code="ad",
        label=t_("自动删除链接消息"),
        desc=t_("解析完成后自动删除用户发送的链接。在群组中需要 bot 有删除消息的权限。"),
        get_value=lambda config: config.auto_delete_url,
        patch=lambda settings, target, value: settings.patch_config(target, auto_delete_url=value),
    ),
    BoolSwitchDTO(
        field="keep_error_log",
        code="el",
        label=t_("保留错误日志"),
        desc=t_("解析出错时错误消息一直保留，关闭时 15 秒后自动删除。"),
        get_value=lambda config: config.keep_error_log,
        patch=lambda settings, target, value: settings.patch_config(target, keep_error_log=value),
    ),
    BoolSwitchDTO(
        field="hide_error",
        code="he",
        label=t_("不显示错误日志"),
        desc=t_("解析出错时不发送错误消息。"),
        get_value=lambda config: config.hide_error,
        patch=lambda settings, target, value: settings.patch_config(target, hide_error=value),
    ),
    BoolSwitchDTO(
        field="noprogress",
        code="np",
        label=t_("禁用解析进度"),
        desc=t_("不再发送解析进度消息，解析完成后直接发送结果。"),
        get_value=lambda config: config.noprogress,
        patch=lambda settings, target, value: settings.patch_config(target, noprogress=value),
    ),
    BoolSwitchDTO(
        field="custom_content",
        code="cc",
        label=t_("自定义文案"),
        desc=t_(
            "启用「自定义文案」后, 在频道 / 私聊中使用 `==文案==` 双等号定界语法, "
            "可将 `文案` 保留样式插入解析结果中 (💡 频道不支持自定义 Emoji)"
        ),
        get_value=lambda config: config.custom_content,
        patch=lambda settings, target, value: settings.patch_config(target, custom_content=value),
        example=t_("https://x.com/i/status/123\n==这里写文案=="),
        image=ASSETS_DIR / "cfg" / "custom_content.png",
    ),
    BoolSwitchDTO(
        field="enable_inline_raw_url",
        code="ir",
        label=t_("内联「原始 URL」选项"),
        desc=t_("内联模式的结果列表中增加「原始链接」选项，选中后只发送链接本身。"),
        get_value=lambda config: config.enable_inline_raw_url,
        patch=lambda settings, target, value: settings.patch_config(target, enable_inline_raw_url=value),
    ),
    BoolSwitchDTO(
        field="rich_mode",
        code="ri",
        label=t_("文章使用富文本发送"),
        desc=t_("文章类内容直接用 Telegram 富文本发送，不再创建 Telegraph 页面。"),
        get_value=lambda config: config.rich_mode,
        patch=lambda settings, target, value: settings.patch_config(target, rich_mode=value),
    ),
)

BOOL_SWITCH_MAP = {switch.code: switch for switch in BOOL_SWITCHES}

SWITCH_GROUPS = (
    SwitchGroupDTO(t_("内容显示"), ("ht", "hd", "hs", "vc", "cc", "ri")),
    SwitchGroupDTO(t_("消息行为"), ("rm", "ad", "np", "ir")),
    SwitchGroupDTO(t_("错误日志"), ("el", "he")),
)
EXPAND_MODE = "mode"
EXPAND_PLATFORM = "plat"
MODE_DESC = t_("直接发送链接时使用的解析方式，使用命令时以命令为准。")
PLATFORM_DESC = t_("关闭后，发送该平台的链接不会被自动解析。")
