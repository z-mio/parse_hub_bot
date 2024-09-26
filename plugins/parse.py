from pyrogram import Client, filters
from pyrogram.types import (
    Message,
)

from utiles.filters import platform_filter
from methods import TgParseHub
from utiles.utile import progress


@Client.on_message(filters.text & platform_filter)
async def call_parse(cli: Client, msg: Message):
    try:
        tph = TgParseHub()
        t = (
            "已有相同任务正在解析, 等待解析完成..."
            if await tph.get_parse_task(msg.text)
            else "解 析 中..."
        )
        r_msg = await msg.reply_text(t)
        pp = await tph.parse(msg.text)
        await pp.download(callback, (r_msg,))
    except Exception as e:
        await msg.reply_text(f"{e}")
        raise e
    else:
        await r_msg.edit_text("上 传 中...")
        try:
            await pp.chat_upload(cli, msg)
        except Exception as e:
            await r_msg.edit_text("上传失败")
            raise e
        await r_msg.delete()


async def callback(current, total, status: str, msg: Message):
    text = progress(current, total, status)
    if not text or msg.text == text:
        return
    await msg.edit_text(text)
    msg.text = text
