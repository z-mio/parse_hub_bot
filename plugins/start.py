from pyrogram import Client, filters
from pyrogram.types import Message, LinkPreviewOptions
from parsehub import ParseHub


@Client.on_message(filters.command(["start", "help"]))
async def start(_, msg: Message):
    await msg.reply(
        f"**直接发送链接即可**\n\n**支持的平台:**\n<blockquote expandable>{get_supported_platforms()}</blockquote>\n\n"
        f"**开源地址: [GitHub](https://github.com/z-mio/parse_hub_bot)**",
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


def get_supported_platforms():
    return "\n".join(ParseHub().get_supported_platforms())
