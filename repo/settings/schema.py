from enum import Enum, StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from db.models.settings import SettingsScope

CURRENT_SCHEMA_VERSION = 1


class ParseMode(StrEnum):
    PREVIEW = "preview"
    RAW = "raw"
    ZIP = "zip"


ALL_SCOPES = frozenset(SettingsScope)

POLICY_SCOPES = frozenset(
    [
        SettingsScope.USER,
        SettingsScope.GROUP,
        SettingsScope.FORUM_TOPIC,
        SettingsScope.CHANNEL,
    ]
)


class MergeStrategy(Enum):
    PREFERENCE = "preference"
    POLICY = "policy"
    UNION = "union"
    STRICT = "strict"


class ConfigMetadata:
    def __init__(self, scopes: frozenset[SettingsScope], merge_strategy: MergeStrategy = MergeStrategy.PREFERENCE):
        self.scopes = frozenset([scopes]) if isinstance(scopes, SettingsScope) else scopes
        self.merge_strategy = merge_strategy


class SettingsConfig(BaseModel):
    model_config = ConfigDict(extra="allow")  # 保留旧字段

    default_mode: Annotated[
        ParseMode,
        Field(description="默认解析模式"),
        ConfigMetadata(ALL_SCOPES, MergeStrategy.PREFERENCE),
    ] = ParseMode.PREVIEW

    auto_delete_url: Annotated[
        bool,
        Field(description="解析完成后自动删除分享链接"),
        ConfigMetadata(ALL_SCOPES, MergeStrategy.PREFERENCE),
    ] = False

    disabled_platforms: Annotated[
        list[str],
        Field(description="禁用的平台"),
        ConfigMetadata(
            POLICY_SCOPES,
            MergeStrategy.POLICY,
        ),
    ] = []

    enable_inline_raw_url: Annotated[
        bool,
        Field(description="启用内联模式的发送原始 URL 功能"),
        ConfigMetadata(frozenset([SettingsScope.USER]), MergeStrategy.STRICT),
    ] = False

    keep_error_log: Annotated[
        bool,
        Field(description="保留错误日志"),
        ConfigMetadata(ALL_SCOPES, MergeStrategy.PREFERENCE),
    ] = False

    hide_source: Annotated[
        bool,
        Field(description="隐藏底部 Source 超链接"),
        ConfigMetadata(ALL_SCOPES, MergeStrategy.PREFERENCE),
    ] = False

    noprogress: Annotated[
        bool,
        Field(description="禁用解析进度, 直接发送结果"),
        ConfigMetadata(POLICY_SCOPES, MergeStrategy.POLICY),
    ] = False

    video_cover: Annotated[
        bool,
        Field(description="启用视频封面"),
        ConfigMetadata(ALL_SCOPES, MergeStrategy.PREFERENCE),
    ] = True

    reply_msg: Annotated[
        bool,
        Field(description="回复消息"),
        ConfigMetadata(ALL_SCOPES, MergeStrategy.PREFERENCE),
    ] = True

    custom_content: Annotated[
        bool,
        Field(description="插入自定义文案到解析结果"),
        ConfigMetadata(frozenset([SettingsScope.CHANNEL, SettingsScope.USER]), MergeStrategy.STRICT),
    ] = False

    hide_title: Annotated[
        bool,
        Field(description="隐藏标题"),
        ConfigMetadata(ALL_SCOPES, MergeStrategy.PREFERENCE),
    ] = False

    hide_desc: Annotated[
        bool,
        Field(description="隐藏简介"),
        ConfigMetadata(ALL_SCOPES, MergeStrategy.PREFERENCE),
    ] = False

    def __str__(self) -> str:
        return self.model_dump_json(indent=4, ensure_ascii=True)


DEFAULT_SETTINGS_CONFIG = SettingsConfig()
