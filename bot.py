import asyncio
import shutil
from typing import Any

import pillow_heif
from pyrogram import Client
from pyrogram.handlers import ConnectHandler, DisconnectHandler
from pyrogram.types import BotCommand

from core import bs, on_connect, on_disconnect, ws
from db.engine import close_db
from db.init import init_db
from i18n import ISO639_MAP
from log import logger, setup_logging
from plugins.helpers import COMMANDS
from services import parse_cache
from utils.event_loop import setup_optimized_event_loop

pillow_heif.register_heif_opener()

setup_logging(debug=bs.debug)

setup_optimized_event_loop()
loop = asyncio.new_event_loop()


class Bot(Client):
    def __init__(self) -> None:
        self.cfg = bs

        super().__init__(
            f"{self.cfg.bot_token.split(':')[0]}_bot",
            api_id=self.cfg.api_id,
            api_hash=self.cfg.api_hash,
            bot_token=self.cfg.bot_token,
            plugins={"root": "plugins"},
            proxy=self.cfg.bot_proxy,
            loop=loop,
            workdir=self.cfg.sessions_path,
        )

    async def bootstrap(self) -> None:
        logger.debug("初始化数据库...")
        await init_db()
        logger.debug("数据库初始化完成")
        parse_cache.start_cleanup()
        self.init_watchdog()

    async def start(self, *args: Any, **kwargs: Any) -> "Bot":
        await self.bootstrap()
        await super().start()
        await self.set_menu()
        return self

    async def stop(self, *args: Any, **kwargs: Any) -> None:
        ws.exit_flag = True
        await super().stop()
        await close_db()
        # 结束时清理下载残留
        if self.cfg.download_dir.exists():
            shutil.rmtree(self.cfg.download_dir)

    def init_watchdog(self) -> None:
        self.add_handler(ConnectHandler(on_connect))
        self.add_handler(DisconnectHandler(on_disconnect))

    async def set_menu(self) -> None:
        commands = await self.get_bot_commands()
        if len(commands) == len(COMMANDS) and all(c.description in str(COMMANDS.values()) for c in commands):
            logger.debug("菜单无变化, 跳过设置")
            return

        for iso639, bcp47 in ISO639_MAP.items():
            tc = {k: v[bcp47] for k, v in COMMANDS.items()}
            await self.set_bot_commands(
                [BotCommand(command=k, description=v) for k, v in tc.items()],
                language_code=iso639,
            )
            logger.debug(f"{iso639 or '默认'} 菜单已设置: {tc}")


if __name__ == "__main__":
    bot = Bot()
    bot.run()
