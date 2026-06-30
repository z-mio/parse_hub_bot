from dataclasses import dataclass
from typing import Unpack

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Users
from repo import UserSettingsRepo, UsersRepo
from repo.user_settings import UserConfig, UserConfigPatch


@dataclass
class AccountContext:
    user: Users
    config: UserConfig

    @property
    def lang(self) -> str:
        return self.user.language_code


class AccountService:
    def __init__(self, session: AsyncSession, telegram_user_id: int) -> None:
        self.telegram_user_id = telegram_user_id
        self.users = UsersRepo(session)
        self.settings = UserSettingsRepo(session)

    async def ensure_account(self) -> AccountContext:
        user = await self.users.ensure_by_telegram_user_id(self.telegram_user_id)
        config = await self.settings.get_config(user.id)
        return AccountContext(user=user, config=config)

    async def get_lang(self) -> str:
        current = await self.ensure_account()
        return current.lang

    async def get_config(self) -> UserConfig:
        current = await self.ensure_account()
        return current.config

    async def set_language(self, language_code: str) -> AccountContext:
        current = await self.ensure_account()
        current.user.language_code = language_code
        return current

    async def save_config(self, config: UserConfig) -> AccountContext:
        current = await self.ensure_account()
        await self.settings.save_config(current.user.id, config)
        return AccountContext(user=current.user, config=config)

    async def patch_config(self, **kwargs: Unpack[UserConfigPatch]) -> AccountContext:
        current = await self.ensure_account()
        config = current.config.model_copy(update=kwargs)
        config = UserConfig.model_validate(config.model_dump())
        await self.settings.save_config(current.user.id, config)
        return AccountContext(user=current.user, config=config)
