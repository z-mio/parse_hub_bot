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
    platforms: dict[str, Platform] = {}

    @classmethod
    def load_config(cls, file: str | Path):
        path = Path(file)
        if not path.exists():
            logger.info("未找到 platform_config.yaml, 跳过加载")
            return cls()

        with open(path, encoding="utf-8") as f:
            data = safe_load(f)

        if not isinstance(data, dict) or data.get("platforms") is None:
            logger.info("platform_config.yaml 为空, 跳过加载")
            return cls()

        platforms = {}
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
        return cls(platforms=platforms)

    def get(self, pid: str) -> Platform | None:
        return self.platforms.get(pid)


platforms_config = PlatformsConfig.load_config(bs.config_path / "platform_config.yaml")
