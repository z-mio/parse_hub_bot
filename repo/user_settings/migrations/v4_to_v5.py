from repo.user_settings.schema import UserConfig


def migrate(config: UserConfig) -> UserConfig:
    return config.model_copy(update={"schema_version": 5, "keep_error_log": False})
