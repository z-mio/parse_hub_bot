from urllib.parse import urlparse

from dotenv import load_dotenv
from os import getenv
from parsehub.config import GlobalConfig

load_dotenv()


class BotConfig:
    def __init__(self):
        self.bot_token = getenv("BOT_TOKEN")
        self.api_id = getenv("API_ID")
        self.api_hash = getenv("API_HASH")
        self.bot_proxy: None | BotConfig._Proxy = self._Proxy(getenv("BOT_PROXY", None))
        self.parser_proxy: None | str = getenv("PARSER_PROXY", None)
        self.downloader_proxy: None | str = getenv("DOWNLOADER_PROXY", None)

        self.cache_time = (
            int(ct) if (ct := getenv("CACHE_TIME")) else 24 * 60 * 60
        )  # 24 hours
        self.ai_summary = bool(getenv("AI_SUMMARY").lower() == "true")
        self.douyin_api = getenv("DOUYIN_API", None)

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


bot_cfg = BotConfig()
if bot_cfg.douyin_api:
    GlobalConfig.douyin_api = bot_cfg.douyin_api
GlobalConfig.duration_limit = 1800
