from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    LinkPreviewOptions,
)

from log import logger
from utiles.filters import platform_filter
from methods import TgParseHub
from utiles.utile import progress


@Client.on_message((filters.text | filters.caption) & platform_filter)
async def call_parse(cli: Client, msg: Message):
    try:
        tph = TgParseHub()
        t = (
            "已有相同任务正在解析, 等待解析完成..."
            if await tph.get_parse_task(msg.text or msg.caption)
            else "解 析 中..."
        )
        r_msg = await msg.reply_text(t)
        pp = await tph.parse(msg.text or msg.caption)
        await pp.download(callback, (r_msg,))
    except Exception as e:
        await msg.reply_text(
            f"解析或下载错误: \n```\n{e}```",
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        logger.exception(e)
        logger.error("解析或下载失败, 以上为错误信息")
    else:
        await r_msg.edit_text("上 传 中...")
        try:
            await pp.chat_upload(cli, msg)
        except Exception as e:
            await r_msg.edit_text("上传失败")
            logger.exception(e)
            logger.error("上传失败, 以上为错误信息")
        await r_msg.delete()


async def callback(current, total, status: str, msg: Message):
    text = progress(current, total, status)
    if not text or msg.text == text:
        return
    await msg.edit_text(text)
    msg.text = text
