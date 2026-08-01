from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Self

from easy_ai18n import PostLocaleSelector

from i18n import t_
from repo.settings import SettingsConfig
from services import SettingsService
from services.settings import AnySettingsTarget


class CfgAction(StrEnum):
    SELECT_TARGET = "t"
    SET_MODE = "m"
    TOGGLE_BOOL = "b"
    TOGGLE_PLATFORM = "p"
    OPEN_PAGE = "o"
    DONE = "d"


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

    @classmethod
    def parse(cls, data: str | bytes) -> Self:
        parts = str(data).split("|")
        _, action, value, *rest = parts
        scope = CfgScopeCode(rest[0]) if rest else None
        channel_id = int(rest[1]) if len(rest) > 1 and rest[1] else None
        user_id = int(rest[2]) if len(rest) > 2 and rest[2] else None
        return cls(action=CfgAction(action), value=value, scope=scope, channel_id=channel_id, user_id=user_id)

    def unparse(self) -> str:
        parts = ["cfg", self.action.value, self.value]
        if not self.scope:
            return "|".join(parts)
        parts.append(self.scope.value)
        if self.channel_id is not None or self.user_id is not None:
            parts.append(str(self.channel_id) if self.channel_id is not None else "")
        if self.user_id is not None:
            parts.append(str(self.user_id))
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
    label: PostLocaleSelector
    get_value: Callable[[SettingsConfig], bool]
    patch: Callable[[SettingsService, AnySettingsTarget, bool], Awaitable[SettingsConfig]]


BOOL_SWITCHES = (
    BoolSwitchDTO(
        field="hide_title",
        code="ht",
        label=t_("隐藏标题"),
        get_value=lambda config: config.hide_title,
        patch=lambda settings, target, value: settings.patch_config(target, hide_title=value),
    ),
    BoolSwitchDTO(
        field="hide_desc",
        code="hd",
        label=t_("隐藏简介"),
        get_value=lambda config: config.hide_desc,
        patch=lambda settings, target, value: settings.patch_config(target, hide_desc=value),
    ),
    BoolSwitchDTO(
        field="video_cover",
        code="vc",
        label=t_("视频封面"),
        get_value=lambda config: config.video_cover,
        patch=lambda settings, target, value: settings.patch_config(target, video_cover=value),
    ),
    BoolSwitchDTO(
        field="reply_msg",
        code="rm",
        label=t_("回复消息"),
        get_value=lambda config: config.reply_msg,
        patch=lambda settings, target, value: settings.patch_config(target, reply_msg=value),
    ),
    BoolSwitchDTO(
        field="hide_source",
        code="hs",
        label=t_("隐藏底部「Source」"),
        get_value=lambda config: config.hide_source,
        patch=lambda settings, target, value: settings.patch_config(target, hide_source=value),
    ),
    BoolSwitchDTO(
        field="auto_delete_url",
        code="ad",
        label=t_("自动删除链接消息"),
        get_value=lambda config: config.auto_delete_url,
        patch=lambda settings, target, value: settings.patch_config(target, auto_delete_url=value),
    ),
    BoolSwitchDTO(
        field="keep_error_log",
        code="el",
        label=t_("保留错误日志"),
        get_value=lambda config: config.keep_error_log,
        patch=lambda settings, target, value: settings.patch_config(target, keep_error_log=value),
    ),
    BoolSwitchDTO(
        field="noprogress",
        code="np",
        label=t_("禁用解析进度"),
        get_value=lambda config: config.noprogress,
        patch=lambda settings, target, value: settings.patch_config(target, noprogress=value),
    ),
    BoolSwitchDTO(
        field="custom_content",
        code="cc",
        label=t_("自定义文案"),
        get_value=lambda config: config.custom_content,
        patch=lambda settings, target, value: settings.patch_config(target, custom_content=value),
    ),
    BoolSwitchDTO(
        field="enable_inline_raw_url",
        code="ir",
        label=t_("内联「原始 URL」选项"),
        get_value=lambda config: config.enable_inline_raw_url,
        patch=lambda settings, target, value: settings.patch_config(target, enable_inline_raw_url=value),
    ),
)

BOOL_SWITCH_MAP = {switch.code: switch for switch in BOOL_SWITCHES}
