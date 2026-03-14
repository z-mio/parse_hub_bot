import asyncio
import shutil

from markdown import markdown
from parsehub import AnyParseResult, Platform
from parsehub.types import (
    AniRef,
    ImageRef,
    ParseResult,
    PostType,
    ProgressUnit,
    VideoRef,
)
from parsehub.utils.media_info import MediaInfoReader
from pyrogram import Client
from pyrogram.errors import MessageNotModified
from pyrogram.types import (
    ChosenInlineResult,
    InlineQuery,
    InlineQueryResultAnimation,
    InlineQueryResultArticle,
    InlineQueryResultPhoto,
    InlineQueryResultVideo,
    InputMediaVideo,
    InputTextMessageContent,
    LinkPreviewOptions,
)
from pyrogram.types import (
    InlineKeyboardButton as Ikb,
)
from pyrogram.types import (
    InlineKeyboardMarkup as Ikm,
)

from log import logger
from plugins.helpers import ProcessedMedia, build_caption, create_telegraph_page, progress
from plugins.start import get_supported_platforms
from services import ParseService
from utils.converter import clean_article_html
from utils.filters import platform_filter
from utils.media_processing_unit import MediaProcessingUnit

DEFAULT_THUMB_URL = "https://telegra.ph/file/cdfdb65b83a4b7b2b6078.png"


async def build_inline_results(parse_result: AnyParseResult, cli: Client) -> list:
    """根据解析结果构建内联查询结果列表"""
    title = parse_result.title or "无标题"
    media_list = parse_result.media if isinstance(parse_result.media, list) else [parse_result.media]
    reply_markup = Ikm([[Ikb("原链接", url=parse_result.raw_url)]])

    results = []

    # ── 富文本直接 telegraph 发送 ──
    if parse_result.type == PostType.RICHTEXT:
        if parse_result.platform == Platform.WEIXIN:
            url = await create_telegraph_page(
                clean_article_html(
                    markdown(parse_result.markdown_content.replace("mmbiz.qpic.cn", "mmbiz.qpic.cn.in"))
                ),
                cli,
                parse_result,
            )
        elif parse_result.platform == Platform.COOLAPK:
            url = await create_telegraph_page(
                clean_article_html(
                    markdown(parse_result.markdown_content.replace("image.coolapk.com", "qpic.cn.in/image.coolapk.com"))
                ),
                cli,
                parse_result,
            )
        else:
            url = await create_telegraph_page(
                clean_article_html(markdown(parse_result.markdown_content)), cli, parse_result
            )
        caption = build_caption(parse_result, url)
        results.append(
            InlineQueryResultArticle(
                title=title,
                description=parse_result.content,
                input_message_content=InputTextMessageContent(
                    caption,
                    link_preview_options=LinkPreviewOptions(show_above_text=True),
                ),
                reply_markup=reply_markup,
            )
        )
        return results

    caption = build_caption(parse_result)

    if not media_list:
        results.append(
            InlineQueryResultArticle(
                title=title,
                description=parse_result.content,
                input_message_content=InputTextMessageContent(
                    caption,
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                ),
                reply_markup=reply_markup,
            )
        )
        return results

    for index, media_ref in enumerate(media_list):
        if isinstance(media_ref, ImageRef):
            results.append(
                InlineQueryResultPhoto(
                    media_ref.url,
                    thumb_url=media_ref.thumb_url,
                    photo_width=media_ref.width or 300,
                    photo_height=media_ref.height or 300,
                    caption=caption,
                    title=title,
                    description=parse_result.content,
                    reply_markup=reply_markup,
                )
            )
        elif isinstance(media_ref, VideoRef):
            results.append(
                InlineQueryResultPhoto(
                    media_ref.thumb_url or DEFAULT_THUMB_URL,
                    photo_width=media_ref.width or 300,
                    photo_height=media_ref.height or 300,
                    id=f"download_{index}",
                    title=caption,
                    caption=caption,
                    reply_markup=reply_markup,
                )
            )
        elif isinstance(media_ref, AniRef):
            if media_ref.ext != "gif":
                results.append(
                    InlineQueryResultVideo(
                        media_ref.url,
                        media_ref.thumb_url or DEFAULT_THUMB_URL,
                        caption=caption,
                        title=title,
                        description=parse_result.content,
                        reply_markup=reply_markup,
                    )
                )
            else:
                results.append(
                    InlineQueryResultAnimation(
                        media_ref.url,
                        thumb_url=media_ref.thumb_url,
                        caption=caption,
                        title=title,
                        description=parse_result.content,
                        reply_markup=reply_markup,
                    )
                )

    return results


@Client.on_inline_query(~platform_filter)
async def inline_parse_tip(_, inline_query: InlineQuery):
    results = [
        InlineQueryResultArticle(
            title="聚合解析",
            description="请在聊天框输入链接",
            input_message_content=InputTextMessageContent(get_supported_platforms()),
            thumb_url="https://i.imgloc.com/2023/06/15/Vbfazk.png",
        )
    ]
    await inline_query.answer(results=results, cache_time=1)


@Client.on_inline_query(platform_filter)
async def call_inline_parse(cli: Client, inline_query: InlineQuery):
    parse_result = await ParseService(inline_query.query).parse()
    results = await build_inline_results(parse_result, cli)
    return await inline_query.answer(results[:50], cache_time=0)


@Client.on_chosen_inline_result()
async def inline_result_download(client: Client, chosen_result: ChosenInlineResult):
    """处理内联结果选择事件，下载并上传视频"""

    if not chosen_result.result_id.startswith("download_"):
        return

    media_index = int(chosen_result.result_id.split("_")[1])
    inline_message_id = chosen_result.inline_message_id

    # ── 解析 ──
    try:
        parse_result = await ParseService(chosen_result.query).parse()
    except Exception as e:
        logger.exception(e)
        logger.error("内联解析失败, 以上为错误信息")
        await client.edit_inline_text(
            inline_message_id,
            f"解析错误: \n```\n{e}```",
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        return

    caption = build_caption(parse_result)

    # ── 下载 ──
    try:
        await client.edit_inline_text(inline_message_id, f"{caption}\n**▎下 载 中...**")
        download_result = await parse_result.download(
            callback=ProgressCallback(),
            callback_args=(client, inline_message_id, parse_result),
        )
    except Exception as e:
        logger.exception(e)
        logger.error("内联下载失败, 以上为错误信息")
        await client.edit_inline_text(
            inline_message_id,
            f"下载错误: \n```\n{e}```",
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        await asyncio.sleep(5)
        await client.edit_inline_text(
            inline_message_id,
            caption,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        return

    # ── 格式转换 ──
    try:
        await client.edit_inline_text(inline_message_id, f"{caption}\n**▎格式转换中...**")
        processed_dir = download_result.output_dir.joinpath("processed")
        processor = MediaProcessingUnit(processed_dir)
        media_files = download_result.media if isinstance(download_result.media, list) else [download_result.media]
        processed_list: list[ProcessedMedia] = []
        for media_file in media_files:
            result = await processor.process(media_file.path)
            processed_list.append(ProcessedMedia(media_file, result.output_paths, result.temp_dir))
    except Exception as e:
        logger.exception(e)
        logger.error("格式转换失败, 以上为错误信息")
        await client.edit_inline_text(
            inline_message_id,
            f"格式转换错误: \n```\n{e}```",
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        await asyncio.sleep(5)
        await client.edit_inline_text(
            inline_message_id,
            caption,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        shutil.rmtree(download_result.output_dir, ignore_errors=True)
        return

    # ── 上传 ──
    await client.edit_inline_text(
        inline_message_id,
        f"{caption}\n**▎上 传 中...**",
    )

    processed = processed_list[media_index]
    video_ref: VideoRef = (
        parse_result.media[media_index] if isinstance(parse_result.media, list) else parse_result.media
    )
    thumb_url = video_ref.thumb_url if video_ref else None

    try:
        file_paths = processed.output_paths or [processed.source.path]
        file_path = file_paths[0]
        file_path_str = str(file_path)
        width = processed.source.width
        height = processed.source.height
        duration = getattr(processed.source, "duration", 0)

        if processed.output_paths:
            media_info = MediaInfoReader.read(file_path_str)
            width, height, duration = (
                media_info.width,
                media_info.height,
                media_info.duration,
            )

        await client.edit_inline_media(
            inline_message_id,
            media=InputMediaVideo(
                file_path_str,
                caption=caption,
                video_cover=thumb_url,
                duration=duration or 0,
                width=width or 0,
                height=height or 0,
                supports_streaming=True,
            ),
        )
    except Exception as e:
        logger.exception(e)
        logger.error("内联上传失败, 以上为错误信息")
        await client.edit_inline_text(
            inline_message_id,
            f"上传错误: \n```\n{e}```",
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        await asyncio.sleep(5)
        await client.edit_inline_text(
            inline_message_id,
            caption,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        shutil.rmtree(download_result.output_dir, ignore_errors=True)


class ProgressCallback:
    async def __call__(
        self,
        current: int,
        total: int,
        unit: ProgressUnit,
        client: Client,
        inline_message_id: str,
        parse_result: ParseResult,
        *args,
    ) -> None:
        progress_text = progress(current, total, unit)
        if not progress_text:
            return
        display_text = f"{build_caption(parse_result)}\n**▎{progress_text}**"
        try:
            await client.edit_inline_text(inline_message_id, display_text)
        except MessageNotModified:
            ...
