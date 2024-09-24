from urllib.parse import urlparse

from dotenv import load_dotenv
from os import getenv

load_dotenv()
HELP_TEXT = (
    "**支持的平台:**\n\n"
    "抖音视频|图文、哔哩哔哩视频|动态、YouTube、YouTube Music、"
    "TikTok视频|图文、小红书视频|图文、Twitter视频|图文、"
    "百度贴吧图文|视频、Facebook视频、微博视频|图文"
)


class BotConfig:
    def __init__(self):
        self.bot_token = getenv("BOT_TOKEN")
        self.api_id = getenv("API_ID")
        self.api_hash = getenv("API_HASH")
        self.proxy: None | BotConfig._Proxy = self._Proxy(getenv("PROXY", None))

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
