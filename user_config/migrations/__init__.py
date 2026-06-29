from collections.abc import Callable

# key = 源版本号，value = 迁移到 key+1 的函数
REGISTRY: dict[int, Callable[[dict], dict]] = {}

__all__ = ["REGISTRY"]
