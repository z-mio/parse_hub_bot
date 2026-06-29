from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase


class Base(AsyncAttrs, DeclarativeBase):
    def __str__(self) -> str:
        kv = ", ".join(f"{k}={v}" for k, v in self.__dict__.items() if not k.startswith("_"))
        return f"{self.__class__.__name__}({kv})"

    def __repr__(self) -> str:
        return self.__str__()
