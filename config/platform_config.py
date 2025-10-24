import random
from dataclasses import dataclass
from pathlib import Path

from yaml import safe_load


@dataclass
class PlatformsConfig:
    platforms: dict[str, "Platform"]

    @classmethod
    def load_config(cls, file: str | Path):
        if Path(file).exists():
            with open(file, encoding="utf-8") as f:
                platforms: dict = safe_load(f).get("platforms")
                if not platforms:
                    return cls({})
                return cls(platforms={k: Platform(**v) for k, v in platforms.items()})
        return cls({})


@dataclass
class Platform:
    disable_parser_proxy: bool = False
    disable_downloader_proxy: bool = False
    parser_proxies: list | None = None
    downloader_proxies: list | None = None
    cookies: list | None = None

    @property
    def cookie(self):
        if not self.cookies:
            return None
        return random.choice(self.cookies)

    @property
    def parser_proxy(self):
        if not self.parser_proxies:
            return None
        return random.choice(self.parser_proxies)

    @property
    def downloader_proxy(self):
        if not self.downloader_proxies:
            return None
        return random.choice(self.downloader_proxies)

    def __post_init__(self):
        if not self.disable_downloader_proxy:
            if isinstance(self.parser_proxies, str):
                self.parser_proxies = [self.parser_proxies]

        if not self.disable_downloader_proxy:
            if isinstance(self.downloader_proxies, str):
                self.downloader_proxies = [self.downloader_proxies]

        if isinstance(self.cookies, str):
            self.cookies = [self.cookies]


platforms_config = PlatformsConfig.load_config(Path.cwd() / "platform_config.yaml")
