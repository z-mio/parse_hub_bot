from parsehub import ParseHub
from pyrogram import Client, filters
from pyrogram.types import BotCommand, LinkPreviewOptions, Message


@Client.on_message(filters.command(["start", "help"]))
async def start(_, msg: Message):
    await msg.reply(
        f"**发送分享链接以进行解析**\n\n"
        f"**支持的平台:**\n"
        f"<blockquote expandable>{get_supported_platforms()}</blockquote>\n\n"
        f"**命令列表:**\n"
        f"`/jx <链接>` - 解析并发送媒体\n"
        f"`/raw <链接>` - 不处理媒体, 发送原始文件\n\n"
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
    commands = {
        "start": "开始",
        "jx": "解析",
        "raw": "不处理媒体并以文件形式发送",
    }
    await cli.set_bot_commands([BotCommand(command=k, description=v) for k, v in commands.items()])
    await msg.reply("👌")
