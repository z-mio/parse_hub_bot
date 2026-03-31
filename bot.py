import asyncio
import shutil

import pillow_heif
from pyrogram import Client
from pyrogram.handlers import ConnectHandler, DisconnectHandler
from pyrogram.types import BotCommand

from core import bs, on_connect, on_disconnect, ws
from log import logger, setup_logging
from services import parse_cache, persistent_cache
from utils.event_loop import setup_optimized_event_loop

pillow_heif.register_heif_opener()

setup_logging(debug=bs.debug)

setup_optimized_event_loop()
loop = asyncio.new_event_loop()


class Bot(Client):
    def __init__(self):
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

    async def start(self, *args, **kwargs):
        self.init_watchdog()
        parse_cache.start_cleanup()
        persistent_cache.start_cleanup()
        await super().start()
        await self.set_menu()

    async def stop(self, *args, **kwargs):
        ws.exit_flag = True
        await super().stop()
        # 结束时清理下载残留
        if self.cfg.download_dir.exists():
            shutil.rmtree(self.cfg.download_dir)

    def init_watchdog(self):
        self.add_handler(ConnectHandler(on_connect))
        self.add_handler(DisconnectHandler(on_disconnect))

    async def set_menu(self):
        commands = {
            "start": "开始",
            "jx": "解析",
            "raw": "不处理媒体, 发送原始文件",
            "zip": "不处理媒体, 保存解析结果, 发送压缩包",
        }
        await self.set_bot_commands([BotCommand(command=k, description=v) for k, v in commands.items()])
        logger.debug(f"菜单已设置: {commands}")


if __name__ == "__main__":
    bot = Bot()
    bot.run()
