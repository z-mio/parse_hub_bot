import os
import random
from pathlib import Path
from typing import Any

from parsehub.types import Platform as PPlatform
from pydantic import AnyUrl, BaseModel, ConfigDict, SecretStr, ValidationError, field_serializer
from yaml import YAMLError, safe_dump, safe_load

from log import logger
from utils.helpers import mask_secret

from .config import bs

logger = logger.bind(name="PlatformConfig")

PLATFORM_CONFIG_FILE = bs.config_path / "platform_config.yaml"
PROXY_SCHEMES = ("http", "https", "socks5", "socks5h")


class PlatformConfigError(ValueError):
    pass


class MaskedSecretStr(SecretStr):
    def _display(self) -> str:
        value = self._secret_value
        return mask_secret(value)


def url_str(url: AnyUrl) -> str:
    """去掉 AnyUrl 自动补上的根路径 `/`"""
    s = str(url)
    if url.path == "/" and not url.query and not url.fragment and s.endswith("/"):
        return s[:-1]
    return s


class Platform(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disable_parser_proxy: bool = False
    disable_downloader_proxy: bool = False
    parser_proxies: list[AnyUrl] | None = None
    downloader_proxies: list[AnyUrl] | None = None
    cookies: list[MaskedSecretStr] | None = None

    @field_serializer("cookies")
    def serialize_cookies(self, cookies: list[SecretStr] | None) -> list[str] | None:
        if cookies is None:
            return None
        return [str(cookie) for cookie in cookies]

    def roll_cookie(self) -> MaskedSecretStr | None:
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

    def to_data(self) -> dict[str, Any]:
        """导出为可写回 yaml 的数据, cookie 为明文"""
        data: dict[str, Any] = {}
        if self.disable_parser_proxy:
            data["disable_parser_proxy"] = True
        if self.disable_downloader_proxy:
            data["disable_downloader_proxy"] = True
        if self.parser_proxies is not None:
            data["parser_proxies"] = [url_str(u) for u in self.parser_proxies]
        if self.downloader_proxies is not None:
            data["downloader_proxies"] = [url_str(u) for u in self.downloader_proxies]
        if self.cookies:
            data["cookies"] = [c.get_secret_value() for c in self.cookies]
        return data


class PlatformsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_parser_proxies: list[AnyUrl] | None = None
    default_downloader_proxies: list[AnyUrl] | None = None
    platforms: dict[str, Platform] = {}

    @classmethod
    def load_config(cls, file: Path) -> "PlatformsConfig":
        try:
            return cls.read_file(file)
        except PlatformConfigError as e:
            logger.error(str(e))
            raise SystemExit(1) from e

    @classmethod
    def read_file(cls, file: Path) -> "PlatformsConfig":
        """读取配置文件, 配置有误时抛出 PlatformConfigError"""
        if not file.exists():
            logger.info("未找到 platform_config.yaml, 跳过加载")
            return cls()

        try:
            with open(file, encoding="utf-8") as f:
                data = safe_load(f)
        except YAMLError as e:
            raise PlatformConfigError(f"platform_config.yaml 格式错误:\n{e}") from e

        if not data:
            logger.info("platform_config.yaml 为空, 跳过加载")
            return cls()

        pc = cls.from_data(data)
        logger.debug(f"已载入平台配置: {pc.model_dump_json(indent=4)}")
        return pc

    @classmethod
    def from_data(cls, data: Any) -> "PlatformsConfig":
        if not isinstance(data, dict):
            raise PlatformConfigError("platform_config.yaml 顶层必须是键值对")

        platforms = {}
        if data.get("platforms"):
            pid_list = [p.id for p in PPlatform]
            for name, pdata in data["platforms"].items():
                if name not in pid_list:
                    raise PlatformConfigError(f"平台 [{name}] 不存在, 支持的平台id: {pid_list}")

                if not pdata:
                    continue

                try:
                    platforms[name] = Platform(**pdata)
                except (ValidationError, TypeError) as e:
                    raise PlatformConfigError(f"平台 [{name}] 配置错误:\n{e}") from e

        try:
            return cls(
                default_parser_proxies=cls._2l(data.get("default_parser_proxies", None)),
                default_downloader_proxies=cls._2l(data.get("default_downloader_proxies", None)),
                platforms=platforms,
            )
        except ValidationError as e:
            raise PlatformConfigError(f"全局默认代理配置错误:\n{e}") from e

    def to_data(self) -> dict[str, Any]:
        """导出为可写回 yaml 的数据, cookie 为明文"""
        data: dict[str, Any] = {}
        if self.default_parser_proxies is not None:
            data["default_parser_proxies"] = [url_str(u) for u in self.default_parser_proxies]
        if self.default_downloader_proxies is not None:
            data["default_downloader_proxies"] = [url_str(u) for u in self.default_downloader_proxies]
        platforms = {pid: pdata for pid, p in self.platforms.items() if (pdata := p.to_data())}
        if platforms:
            data["platforms"] = platforms
        return data

    def save(self, file: Path) -> None:
        """原子写入配置文件"""
        tmp = file.with_name(f"{file.name}.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            safe_dump(self.to_data(), f, allow_unicode=True, sort_keys=False)
        os.replace(tmp, file)

    def update_from(self, other: "PlatformsConfig") -> None:
        """原地替换为另一份配置, 已导入 pl_cfg 的模块会同步看到新值"""
        for name in type(self).model_fields:
            setattr(self, name, getattr(other, name))

    @staticmethod
    def _2l[T](v: T | list[T] | None) -> list[T] | None:
        if v is None:
            return None
        if isinstance(v, list):
            return v
        return [v]

    def get(self, platform_id: str) -> Platform | None:
        return self.platforms.get(platform_id)

    def roll_cookie(self, platform_id: str) -> MaskedSecretStr | None:
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


pl_cfg = PlatformsConfig.load_config(PLATFORM_CONFIG_FILE)
