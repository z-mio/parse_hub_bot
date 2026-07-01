from typing import Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field

CURRENT_SCHEMA_VERSION = 3

DefaultMode = Literal["preview", "raw", "zip"]


class UserConfig(BaseModel):
    model_config = ConfigDict(extra="allow")  # 保留旧字段

    schema_version: int = Field(default=CURRENT_SCHEMA_VERSION, ge=1, frozen=True)
    default_mode: DefaultMode = Field(default="preview", description="默认解析模式")
    auto_delete_url: bool = Field(default=False, description="解析完成后自动删除分享链接")
    disabled_platforms: list[str] = Field(default=[], description="禁用的平台")
    """平台 id"""
    enable_inline_raw_url: bool = Field(default=False, description="启用内联模式的发送原始 URL 功能")
    keep_error_log: bool = Field(default=False, description="保留错误日志")

    def __str__(self) -> str:
        return self.model_dump_json(indent=4, ensure_ascii=True)


class UserConfigPatch(TypedDict, total=False):
    default_mode: DefaultMode
    auto_delete_url: bool
    disabled_platforms: list[str]
    enable_inline_raw_url: bool
    keep_error_log: bool


DEFAULT_USER_CONFIG = UserConfig()
