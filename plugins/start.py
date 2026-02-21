from parsehub import ParseHub
from pyrogram import Client, filters
from pyrogram.types import BotCommand, LinkPreviewOptions, Message


@Client.on_message(filters.command(["start", "help"]))
async def start(_, msg: Message):
    await msg.reply(
        f"**直接发送链接即可**\n\n**支持的平台:**\n<blockquote expandable>{get_supported_platforms()}</blockquote>\n\n"
        f"**开源地址: [GitHub](https://github.com/z-mio/parse_hub_bot)**",
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


def get_supported_platforms():
    text = []
    for i in ParseHub().get_platforms():
        text.append(f"{i['name']}: {'|'.join(i['supported_types'])}")
    return "\n".join(text)


@Client.on_message(filters.command("menu"))
async def set_menu(cli: Client, msg: Message):
    commands = {"start": "开始", "jx": "解析"}
    await cli.set_bot_commands([BotCommand(command=k, description=v) for k, v in commands.items()])
    await msg.reply("👌")
