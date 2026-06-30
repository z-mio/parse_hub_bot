from log import logger
from repo.user_settings.migrations import REGISTRY
from repo.user_settings.schema import CURRENT_SCHEMA_VERSION, DEFAULT_USER_CONFIG, UserConfig

logger = logger.bind(name="UserConfigMigration")


def migrate(config: UserConfig | None = None) -> UserConfig:
    """
    按注册表链条逐步升版本，并返回通过 Pydantic 校验后的 UserConfig。
    幂等：已是最新版本时只做模型校验，不修改入参。
    """
    config = config or DEFAULT_USER_CONFIG.model_copy(deep=True)
    if config.schema_version == CURRENT_SCHEMA_VERSION:
        return config

    if config.schema_version > CURRENT_SCHEMA_VERSION:
        raise ValueError(f"未知的 schema_version={config.schema_version}，当前最大版本为 {CURRENT_SCHEMA_VERSION}。")

    logger.debug(f"开始迁移用户配置: schema_version={config.schema_version}, current={CURRENT_SCHEMA_VERSION}")
    while config.schema_version < CURRENT_SCHEMA_VERSION:
        source_version = config.schema_version
        fn = REGISTRY.get(source_version)
        if fn is None:
            raise ValueError(
                f"缺少迁移函数：v{source_version} → v{source_version + 1}，"
                f"请在 migrations/ 下新增文件并注册到 REGISTRY。"
            )

        logger.debug(f"执行用户配置迁移: v{source_version} -> v{source_version + 1}")
        config = fn(config)
        if config.schema_version != source_version + 1:
            raise ValueError(f"迁移函数 v{source_version} 必须返回 schema_version={source_version + 1}。")
        logger.debug(f"用户配置迁移完成: v{source_version} -> v{config.schema_version}")

    validated_config = UserConfig.model_validate(config.model_dump())
    logger.debug(f"用户配置校验完成: schema_version={validated_config.schema_version}")
    return validated_config
