import asyncio

from pyrogram import Client, filters
from pyrogram.types import (
    LinkPreviewOptions,
    Message,
)

from log import logger
from methods import TgParseHub
from utiles.filters import platform_filter
from utiles.utile import progress


async def _handle_parse(cli: Client, msg: Message, text: str):
    tph = TgParseHub()
    t = "已有相同任务正在解析, 等待解析完成..." if await tph.get_parse_task(text) else "解 析 中..."
    r_msg = await msg.reply_text(t)

    try:
        pp = await tph.parse(text)
    except Exception as e:
        logger.exception(e)
        logger.error("解析失败, 以上为错误信息")
        await r_msg.edit_text(
            f"解析错误: \n```\n{e}```",
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        await asyncio.sleep(3)
        await r_msg.delete()
        return

    await r_msg.edit_text("下 载 中...")

    try:
        await pp.download(callback, (r_msg,))
    except Exception as e:
        logger.exception(e)
        logger.error("解析或下载失败, 以上为错误信息")
        await r_msg.edit_text(
            f"下载错误: \n```\n{e}```",
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        await asyncio.sleep(3)
        await r_msg.delete()
    else:
        await r_msg.edit_text("上 传 中...")
        try:
            await pp.chat_upload(cli, msg)
        except Exception as e:
            await r_msg.edit_text("上传失败")
            logger.exception(e)
            logger.error("上传失败, 以上为错误信息")
        await r_msg.delete()


@Client.on_message((filters.text | filters.caption) & platform_filter)
async def text_parse(cli: Client, msg: Message):
    text = msg.text or msg.caption
    await _handle_parse(cli, msg, text)


@Client.on_message(filters.command(["jx"]))
async def cmd_jx(cli: Client, msg: Message):
    if msg.command[1:]:
        text = msg.command[1]
    else:
        text = ""

    if not text and msg.reply_to_message:
        text = msg.reply_to_message.text or msg.reply_to_message.caption or ""

    if not text:
        await msg.reply_text("请加上链接或回复一条消息")
        return

    await _handle_parse(cli, msg, text)


async def callback(current, total, status: str, msg: Message):
    text = progress(current, total, status)
    if not text or msg.text == text:
        return
    await msg.edit_text(text)
    msg.text = text
