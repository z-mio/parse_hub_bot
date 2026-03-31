import random
from pathlib import Path

from parsehub.types import Platform as PPlatform
from pydantic import BaseModel, ConfigDict, HttpUrl
from yaml import safe_load

from log import logger

from .config import bs

logger = logger.bind(name="PlatformConfig")


class Platform(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disable_parser_proxy: bool = False
    disable_downloader_proxy: bool = False
    parser_proxies: list[HttpUrl] | None = None
    downloader_proxies: list[HttpUrl] | None = None
    cookies: list[str] | None = None

    def roll_cookie(self) -> str | None:
        if not self.cookies:
            return None
        return random.choice(self.cookies)

    def roll_parser_proxy(self) -> str | None:
        if not self.parser_proxies:
            return None
        return str(random.choice(self.parser_proxies))

    def roll_downloader_proxy(self) -> str | None:
        if not self.downloader_proxies:
            return None
        return str(random.choice(self.downloader_proxies))


class PlatformsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_parser_proxies: list[HttpUrl] | None = None
    default_downloader_proxies: list[HttpUrl] | None = None
    platforms: dict[str, Platform] = {}

    @classmethod
    def load_config(cls, file: Path):
        if not file.exists():
            logger.info("未找到 platform_config.yaml, 跳过加载")
            return cls()

        with open(file, encoding="utf-8") as f:
            data = safe_load(f)

        if not data:
            logger.info("platform_config.yaml 为空, 跳过加载")
            return cls()

        platforms = {}
        if data.get("platforms"):
            pid_list = [p.id for p in PPlatform]
            for name, pdata in data["platforms"].items():
                if name not in pid_list:
                    logger.error(f"平台 [{name}] 不存在, 支持的平台id: {pid_list}")
                    exit(1)

                if not pdata:
                    continue

                try:
                    platforms[name] = Platform(**pdata)
                except Exception as e:
                    logger.error(f"平台 [{name}] 配置错误:\n{e}")
                    raise SystemExit(1) from e

        pc = cls(
            default_parser_proxies=cls._2l(data.get("default_parser_proxies", None)),
            default_downloader_proxies=cls._2l(data.get("default_downloader_proxies", None)),
            platforms=platforms,
        )
        logger.debug(f"已载入平台配置: {pc.model_dump_json(indent=4)}")
        return pc

    @staticmethod
    def _2l(v) -> list | None:
        if v and not isinstance(v, list):
            return [v]
        return v

    def get(self, platform_id: str) -> Platform | None:
        return self.platforms.get(platform_id)

    def roll_cookie(self, platform_id: str) -> str | None:
        if not (pc := self.get(platform_id)):
            return None
        return pc.roll_cookie()

    def roll_parser_proxy(self, platform_id: str) -> str | None:
        if not (pc := self.get(platform_id)):
            pc = Platform()
        if pc.disable_parser_proxy:
            return None

        if platform_proxy := pc.roll_parser_proxy():
            return platform_proxy
        if self.default_parser_proxies:
            return str(random.choice(self.default_parser_proxies))
        return None

    def roll_downloader_proxy(self, platform_id: str) -> str | None:
        if not (pc := self.get(platform_id)):
            pc = Platform()
        if pc.disable_downloader_proxy:
            return None

        if platform_proxy := pc.roll_downloader_proxy():
            return platform_proxy
        if self.default_downloader_proxies:
            return str(random.choice(self.default_downloader_proxies))
        return None


pl_cfg = PlatformsConfig.load_config(bs.config_path / "platform_config.yaml")
