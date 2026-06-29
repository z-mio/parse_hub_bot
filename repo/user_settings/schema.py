from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CURRENT_SCHEMA_VERSION = 3

DefaultMode = Literal["preview", "raw", "zip"]


class UserConfig(BaseModel):
    model_config = ConfigDict(extra="allow")  # 保留旧字段

    schema_version: int = Field(default=CURRENT_SCHEMA_VERSION, ge=1)
    default_mode: DefaultMode = Field(default="preview", description="默认解析模式")
    auto_delete_url: bool = Field(default=False, description="解析完成后自动删除分享链接")
    disabled_platforms: list[str] = Field(default=[], description="禁用的平台")
    """平台 id"""

    def __str__(self) -> str:
        return self.model_dump_json(indent=4, ensure_ascii=True)


DEFAULT_USER_CONFIG = UserConfig()
