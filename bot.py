from pyrogram import Client
from config.config import bot_cfg
from log import logger

logger.add("logs/bot.log", rotation="10 MB")


class Bot(Client):
    def __init__(self):
        self.cfg = bot_cfg

        super().__init__(
            f"{self.cfg.bot_token.split(':')[0]}_bot",
            api_id=self.cfg.api_id,
            api_hash=self.cfg.api_hash,
            bot_token=self.cfg.bot_token,
            plugins=dict(root="plugins"),
            proxy=self.cfg.bot_proxy.dict_format,
        )

    async def start(self):
        logger.info("Bot开始运行...")
        await super().start()

    async def stop(self, *args):
        await super().stop()


if __name__ == "__main__":
    bot = Bot()
    bot.run()
