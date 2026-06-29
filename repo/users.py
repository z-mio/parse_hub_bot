from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.users import Users


class UsersRepo:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_all(self) -> list[Users]:
        result = await self._session.scalars(select(Users))
        return list(result.all())

    async def get_by_telegram_user_id(self, telegram_user_id: int) -> Users | None:
        user = await self._session.scalar(select(Users).where(Users.telegram_user_id == telegram_user_id))
        return user

    async def get_or_create_by_telegram_user_id(
        self,
        telegram_user_id: int,
    ) -> Users:
        user = await self.get_by_telegram_user_id(telegram_user_id)
        if user is not None:
            return user

        user = Users(telegram_user_id=telegram_user_id)
        self._session.add(user)
        await self._session.flush()
        return user

    async def add(self, user_id: int) -> Users:
        user = Users(telegram_user_id=user_id)
        self._session.add(user)
        return user
