import asyncio
import sys

import pillow_heif
from pyrogram import Client
from pyrogram.handlers import ConnectHandler, DisconnectHandler

from config.config import bot_cfg, ws
from log import logger, logger_format
from utiles.optimized_event_loop import setup_optimized_event_loop
from utiles.watchdog import on_connect, on_disconnect

pillow_heif.register_heif_opener()


logger.remove()

if bot_cfg.debug:
    logger.add(sys.stderr, level="DEBUG", format=logger_format)
    logger.debug("调试模式已启用")
else:
    logger.add(sys.stderr, level="INFO", format=logger_format)
logger.add(
    "logs/bot.log",
    rotation="10 MB",
    level="INFO",
    format=logger_format,
    # serialize=True,
    enqueue=True,
)

setup_optimized_event_loop()
loop = asyncio.new_event_loop()


class Bot(Client):
    def __init__(self):
        self.cfg = bot_cfg

        super().__init__(
            f"{self.cfg.bot_token.split(':')[0]}_bot",
            api_id=self.cfg.api_id,
            api_hash=self.cfg.api_hash,
            bot_token=self.cfg.bot_token,
            plugins={"root": "plugins"},
            proxy=self.cfg.bot_proxy.dict_format,
            loop=loop,
        )

    async def start(self, *args, **kwargs):
        self.init_watchdog()
        await super().start()

    async def stop(self, *args, **kwargs):
        ws.exit_flag = True
        await super().stop()

    def init_watchdog(self):
        self.add_handler(ConnectHandler(on_connect))
        self.add_handler(DisconnectHandler(on_disconnect))


if __name__ == "__main__":
    bot = Bot()
    bot.run()
