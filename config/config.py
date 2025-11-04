import os
import shutil
from os import getenv
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from parsehub.config import GlobalConfig
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

TEMP_DIR = Path("./temp")
if TEMP_DIR.exists():
    shutil.rmtree(str(TEMP_DIR), ignore_errors=True)
TEMP_DIR.mkdir(exist_ok=True)


class BotConfig:
    def __init__(self):
        self.bot_token = getenv("BOT_TOKEN")
        self.api_id = getenv("API_ID")
        self.api_hash = getenv("API_HASH")
        self.bot_proxy: None | BotConfig._Proxy = self._Proxy(getenv("BOT_PROXY", None))
        self.parser_proxy: None | str = getenv("PARSER_PROXY", None)
        self.downloader_proxy: None | str = getenv("DOWNLOADER_PROXY", None)

        self.cache_time = int(ct) if (ct := getenv("CACHE_TIME")) else 24 * 60 * 60  # 24 hours
        self.ai_summary = bool(getenv("AI_SUMMARY").lower() == "true")
        self.douyin_api = getenv("DOUYIN_API", None)
        self.debug = bool(getenv("DEBUG", "false").lower() == "true")

    class _Proxy:
        def __init__(self, url: str):
            self._url = urlparse(url) if url else None
            self.url = self._url.geturl() if self._url else None

        @property
        def dict_format(self):
            if not self._url:
                return None
            return {
                "scheme": self._url.scheme,
                "hostname": self._url.hostname,
                "port": self._url.port,
                "username": self._url.username,
                "password": self._url.password,
            }


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

    def update_bot_restart_count(self):
        self.restart_count += 1
        os.environ["WD_RESTART_COUNT"] = str(self.restart_count)

    def reset_bot_restart_count(self):
        self.restart_count = 0
        os.environ["WD_RESTART_COUNT"] = "0"

    def update_bot_disconnect_count(self):
        self.disconnect_count += 1
        os.environ["WD_DISCONNECT_COUNT"] = str(self.disconnect_count)

    def reset_bot_disconnect_count(self):
        self.disconnect_count = 0
        os.environ["WD_DISCONNECT_COUNT"] = "0"


bot_cfg = BotConfig()
ws = WatchdogSettings()
if bot_cfg.douyin_api:
    GlobalConfig.douyin_api = bot_cfg.douyin_api
GlobalConfig.duration_limit = 0
