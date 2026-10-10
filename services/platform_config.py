import asyncio
from collections.abc import Callable

from core import PLATFORM_CONFIG_FILE, PlatformsConfig, pl_cfg
from log import logger

from .cookie_health import cookie_health

logger = logger.bind(name="PlatformConfigService")


class PlatformConfigService:
    """平台配置热更新: 校验整份配置 → 原子写回 yaml → 原地更新 pl_cfg"""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    async def edit(self, fn: Callable[[PlatformsConfig], None]) -> None:
        """在副本上执行 fn, 校验通过后保存并生效; fn 或校验抛错时配置不变"""
        async with self._lock:
            draft = pl_cfg.model_copy(deep=True)
            fn(draft)
            self._apply(PlatformsConfig.from_data(draft.to_data()), save=True)

    async def reload(self) -> None:
        """从文件重载, 配置有误时抛出 PlatformConfigError 并保留当前配置"""
        async with self._lock:
            self._apply(PlatformsConfig.read_file(PLATFORM_CONFIG_FILE), save=False)

    def _apply(self, new: PlatformsConfig, *, save: bool) -> None:
        if save:
            new.save(PLATFORM_CONFIG_FILE)
        pl_cfg.update_from(new)
        cookie_health.prune({c.get_secret_value() for p in pl_cfg.platforms.values() for c in p.cookies or []})
        logger.info("平台配置已更新")


platform_config_service = PlatformConfigService()
