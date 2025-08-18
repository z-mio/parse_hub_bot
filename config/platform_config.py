import random
from dataclasses import dataclass
from pathlib import Path

from yaml import safe_load


@dataclass
class PlatformsConfig:
    platforms: dict[str, "Platform"]

    @classmethod
    def load_config(cls, file: str | Path):
        with open(file, "r") as f:
            platforms: dict = safe_load(f)["platforms"]
            cls.platforms = {k: Platform(**v) for k, v in platforms.items()}
        return cls


@dataclass
class Platform:
    disable_parser_proxy: bool = False
    disable_downloader_proxy: bool = False
    parser_proxys: list | None = None
    downloader_proxys: list | None = None
    cookies: list | None = None

    @property
    def cookie(self):
        if not self.cookies:
            return None
        return random.choice(self.cookies)

    @property
    def parser_proxy(self):
        if not self.parser_proxys:
            return None
        return random.choice(self.parser_proxys)

    @property
    def downloader_proxy(self):
        if not self.downloader_proxys:
            return None
        return random.choice(self.downloader_proxys)

    def __post_init__(self):
        if isinstance(self.parser_proxys, str):
            if self.disable_parser_proxy:
                self.parser_proxys = None
            self.parser_proxys = [self.parser_proxys]
        if isinstance(self.downloader_proxys, str):
            if self.disable_downloader_proxy:
                self.downloader_proxys = None
            self.downloader_proxys = [self.downloader_proxys]
        if isinstance(self.cookies, str):
            self.cookies = [self.cookies]


platforms_config = PlatformsConfig.load_config(Path.cwd() / "platform_config.yaml")
