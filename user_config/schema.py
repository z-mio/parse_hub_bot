from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CURRENT_SCHEMA_VERSION = 1

DefaultMode = Literal["preview", "raw", "zip"]


class UserConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: int = Field(default=CURRENT_SCHEMA_VERSION, ge=1)
    default_mode: DefaultMode = "preview"


DEFAULT_USER_CONFIG = UserConfig()
