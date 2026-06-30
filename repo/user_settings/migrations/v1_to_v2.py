from repo.user_settings.schema import UserConfig


def migrate(config: UserConfig) -> UserConfig:
    return config.model_copy(update={"schema_version": 2, "auto_delete_url": False})
