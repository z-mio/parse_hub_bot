from collections.abc import Callable

from repo.user_settings.migrations.v1_to_v2 import migrate as migrate_v1_to_v2
from repo.user_settings.schema import UserConfig

# key = 源版本号，value = 迁移到 key+1 的函数
REGISTRY: dict[int, Callable[[UserConfig], UserConfig]] = {1: migrate_v1_to_v2}

__all__ = ["REGISTRY"]
