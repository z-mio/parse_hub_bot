from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.user_settings import UserSettings
from user_config import DEFAULT_USER_CONFIG, UserConfig, migrate


class UserSettingsRepo:
    def __init__(self, session: AsyncSession):
        self._session = session

    @staticmethod
    def config_from_raw(raw: dict[str, Any] | None) -> UserConfig:
        if raw is None:
            return DEFAULT_USER_CONFIG.model_copy(deep=True)
        data = migrate(raw)
        return UserConfig.model_validate(data)

    async def get(self, user_id: int) -> UserSettings | None:
        return await self._session.scalar(select(UserSettings).where(UserSettings.user_id == user_id))

    async def get_or_create(self, user_id: int) -> UserSettings:
        settings = await self.get(user_id)
        if settings is not None:
            return settings

        config = UserConfig()
        settings = UserSettings(
            user_id=user_id,
            settings_json=config.model_dump(mode="json"),
            schema_version=config.schema_version,
        )
        self._session.add(settings)
        await self._session.flush()
        return settings

    async def get_config(self, user_id: int) -> UserConfig:
        settings = await self.get_or_create(user_id)
        config = self.config_from_raw(settings.settings_json)

        if settings.schema_version != config.schema_version or settings.settings_json != config.model_dump(mode="json"):
            await self.save_config(user_id, config)

        return config

    async def save_config(self, user_id: int, config: UserConfig) -> UserSettings:
        settings = await self.get_or_create(user_id)
        settings.settings_json = config.model_dump(mode="json")
        settings.schema_version = config.schema_version
        await self._session.flush()
        return settings

    async def patch_config(self, user_id: int, **kwargs: Any) -> UserConfig:
        current = await self.get_config(user_id)
        config = current.model_copy(update=kwargs)
        config = UserConfig.model_validate(config.model_dump())

        await self.save_config(user_id, config)
        return config

    async def get_by_user_ids(self, user_ids: list[int]) -> list[UserSettings]:
        if not user_ids:
            return []
        result = await self._session.scalars(select(UserSettings).where(UserSettings.user_id.in_(user_ids)))
        return list(result)

    async def save_raw(self, user_id: int, data: dict[str, Any], schema_version: int) -> UserSettings:
        settings = await self.get_or_create(user_id)
        settings.settings_json = data
        settings.schema_version = schema_version
        await self._session.flush()
        return settings
