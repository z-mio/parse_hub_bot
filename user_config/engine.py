from .migrations import REGISTRY
from .schema import CURRENT_SCHEMA_VERSION


def migrate(prefs: dict) -> dict:
    """
    按注册表链条逐步升版本，直到 CURRENT_VERSION。
    幂等：已是最新版本时直接返回，不做任何修改。

    Args:
        prefs: 从数据库读出的原始 dict（已 json.loads）

    Returns:
        升到最新版本的 dict

    Raises:
        ValueError: 版本号无对应迁移函数时
    """
    version: int = prefs.get("schema_version", 1)

    if version > CURRENT_SCHEMA_VERSION:
        raise ValueError(f"未知的 schema_version={version}，当前最大版本为 {CURRENT_SCHEMA_VERSION}。")

    while version < CURRENT_SCHEMA_VERSION:
        fn = REGISTRY.get(version)
        if fn is None:
            raise ValueError(
                f"缺少迁移函数：v{version} → v{version + 1}，请在 migrations/ 下新增文件并注册到 REGISTRY。"
            )
        prefs = fn(prefs)
        version = prefs["schema_version"]

    return prefs
