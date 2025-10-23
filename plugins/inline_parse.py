from parsehub.types import Video
from pyrogram import Client
from pyrogram.errors import MessageNotModified
from pyrogram.types import (
    InlineQuery,
    InputTextMessageContent,
    InlineQueryResultArticle,
    ChosenInlineResult,
    InputMediaVideo,
    LinkPreviewOptions,
)

from log import logger
from methods import TgParseHub
from plugins.start import get_supported_platforms
from utiles.filters import platform_filter
from utiles.utile import progress


@Client.on_inline_query(~platform_filter)
async def inline_parse_tip(_, iq: InlineQuery):
    results = [
        InlineQueryResultArticle(
            title="聚合解析",
            description="请在聊天框输入链接",
            input_message_content=InputTextMessageContent(get_supported_platforms()),
            thumb_url="https://i.imgloc.com/2023/06/15/Vbfazk.png",
        )
    ]
    await iq.answer(results=results, cache_time=1)


@Client.on_inline_query(platform_filter)
async def call_inline_parse(_, iq: InlineQuery):
    pp = await TgParseHub().parse(iq.query)
    await pp.inline_upload(iq)


async def callback(
    current, total, status: str, client: Client, inline_message_id, pp: TgParseHub
):
    text = progress(current, total, status)
    if not text:
        return
    text = f"{pp.operate.content_and_url}\n\n{text}"
    try:
        await client.edit_inline_text(
            inline_message_id, text, reply_markup=pp.operate.button(hide_summary=True)
        )
    except MessageNotModified:
        ...


@Client.on_chosen_inline_result()
async def inline_result_jx(client: Client, cir: ChosenInlineResult):
    """只用于下载视频"""

    if not cir.result_id.startswith("download_"):
        return
    index = int(cir.result_id.split("_")[1])
    imid = cir.inline_message_id

    try:
        pp = await TgParseHub().parse(cir.query)
        await client.edit_inline_text(
            imid, "下 载 中...", reply_markup=pp.operate.button(hide_summary=True)
        )
        await pp.download(
            callback,
            (client, imid, pp),
        )
    except Exception as e:
        await client.edit_inline_text(
            imid,
            f"解析或下载错误: \n```\n{e}```",
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        logger.exception(e)
        logger.error("解析或下载失败, 以上为错误信息")
    else:
        await client.edit_inline_text(
            imid,
            f"{pp.operate.content_and_url}\n\n上 传 中...",
            reply_markup=pp.operate.button(hide_summary=True),
        )
        v: Video = (
            pp.operate.download_result.media[index]
            if isinstance(pp.operate.download_result.media, list)
            else pp.operate.download_result.media
        )
        await client.edit_inline_media(
            imid,
            media=InputMediaVideo(
                v.path,
                caption=pp.operate.content_and_url,
                video_cover=v.thumb_url,
                duration=v.duration,
                width=v.width,
                height=v.height,
            ),
            reply_markup=pp.operate.button(),
        )
