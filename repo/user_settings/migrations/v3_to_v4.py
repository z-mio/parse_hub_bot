from repo.user_settings.schema import UserConfig


def migrate(config: UserConfig) -> UserConfig:
    return config.model_copy(update={"schema_version": 4, "enable_inline_raw_url": False})
