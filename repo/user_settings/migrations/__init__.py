from collections.abc import Callable

from repo.user_settings.migrations.v1_to_v2 import migrate as migrate_v1_to_v2
from repo.user_settings.migrations.v2_to_v3 import migrate as migrate_v2_to_v3
from repo.user_settings.schema import UserConfig

# key = 源版本号，value = 迁移到 key+1 的函数
REGISTRY: dict[int, Callable[[UserConfig], UserConfig]] = {
    1: migrate_v1_to_v2,
    2: migrate_v2_to_v3,
}

__all__ = ["REGISTRY"]
