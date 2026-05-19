import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = Field(...)
    api_id: str = Field(...)
    api_hash: str = Field(...)
    bot_proxy: dict | None = Field(default=None)
    data_path: Path = Path("data")
    cache_time: int = Field(default=14 * 24 * 60, ge=0, description="缓存时间, 单位分钟, 0 为禁用")
    cache_max_entries: int = Field(default=30000, ge=0, description="缓存最大条数, 0 为不限制")
    cache_save_interval: int = Field(default=5, gt=0, description="缓存保存间隔, 单位分钟")
    cache_cleanup_interval: int = Field(default=60, gt=0, description="缓存过期清理间隔, 单位分钟")
    download_dir: Path = Path("downloads")
    debug: bool = Field(default=False)
    debug_skip_cleanup: bool = Field(default=False, description="跳过资源清理")

    @model_validator(mode="after")
    def cache_config_validate(self) -> "BotSettings":
        if self.cache_time and self.cache_cleanup_interval > self.cache_time:
            raise ValueError("CACHE_CLEANUP_INTERVAL 不能大于 CACHE_TIME")
        return self

    def model_post_init(self, __context: Any) -> None:
        """模型初始化后的操作"""
        self.sessions_path.mkdir(parents=True, exist_ok=True)
        self.cache_path.mkdir(parents=True, exist_ok=True)
        self.config_path.mkdir(parents=True, exist_ok=True)

    @property
    def sessions_path(self) -> Path:
        return self.data_path / "sessions"

    @property
    def cache_path(self) -> Path:
        return self.data_path / "cache"

    @property
    def config_path(self) -> Path:
        return self.data_path / "config"

    @field_validator("bot_proxy", mode="before")
    @classmethod
    def proxy_config(cls, v: str | None = None) -> dict | None:
        url = urlparse(v) if v else None
        if not url:
            return None
        return {
            "scheme": url.scheme,
            "hostname": url.hostname,
            "port": url.port,
            "username": url.username,
            "password": url.password,
        }

    @property
    def bot_session_name(self) -> str:
        return f"bot_{self.bot_token.split(':')[0]}"

    @field_validator("data_path", mode="before")
    @classmethod
    def data_path_init(cls, v: str | Path) -> Path:
        p = Path(v) if isinstance(v, str) else v
        p.mkdir(exist_ok=True, parents=True)
        return p


class WatchdogSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,
        extra="ignore",
        env_prefix="WD_",
    )
    is_running: bool = Field(default=False)
    """运行中"""
    restart_count: int = Field(default=0)
    """重启次数"""
    disconnect_count: int = Field(default=0)
    """断开连接次数"""
    max_disconnect_count: int = Field(default=3)
    """最大断开连接次数, 超过后重启"""
    remove_session_after_restart: int = Field(default=3)
    """重启失败几次后删除会话文件"""
    max_restart_count: int = Field(default=6)
    """意外断开连接时，最大重启次数"""
    exit_flag: bool = Field(default=False)
    """退出标志"""

    def update_bot_restart_count(self) -> None:
        self.restart_count += 1
        os.environ["WD_RESTART_COUNT"] = str(self.restart_count)

    def reset_bot_restart_count(self) -> None:
        self.restart_count = 0
        os.environ["WD_RESTART_COUNT"] = "0"

    def update_bot_disconnect_count(self) -> None:
        self.disconnect_count += 1
        os.environ["WD_DISCONNECT_COUNT"] = str(self.disconnect_count)

    def reset_bot_disconnect_count(self) -> None:
        self.disconnect_count = 0
        os.environ["WD_DISCONNECT_COUNT"] = "0"


bs = BotSettings()  # type: ignore[call-arg]
ws = WatchdogSettings()
