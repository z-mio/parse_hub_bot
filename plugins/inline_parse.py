import asyncio

from parsehub import AnyParseResult
from parsehub.types import (
    AniRef,
    ImageRef,
    PostType,
    VideoRef,
)
from parsehub.utils.media_info import MediaInfoReader
from pyrogram import Client
from pyrogram.types import (
    ChosenInlineResult,
    InlineQuery,
    InlineQueryResultAnimation,
    InlineQueryResultArticle,
    InlineQueryResultCachedDocument,
    InlineQueryResultCachedPhoto,
    InlineQueryResultCachedVideo,
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
from plugins.helpers import build_caption, build_caption_by_str, create_richtext_telegraph
from plugins.start import get_supported_platforms
from services import ParseService
from services.cache import CacheEntry, CacheMedia, CacheMediaType, CacheParseResult, parse_cache, persistent_cache
from services.pipeline import ParsePipeline, StatusReporter
from utils.filters import platform_filter

logger = logger.bind(name="InlineParse")
DEFAULT_THUMB_URL = "https://telegra.ph/file/cdfdb65b83a4b7b2b6078.png"


class InlineStatusReporter(StatusReporter):
    """基于 inline_message_id 的状态报告器"""

    def __init__(self, client: Client, inline_message_id: str, caption: str = ""):
        self._client = client
        self._mid = inline_message_id
        self._caption = caption
        self._last_text: str | None = None

    async def report(self, text: str) -> None:
        full = f"{self._caption}\n{text}" if self._caption else text
        if full == self._last_text:
            return
        self._last_text = full
        try:
            await self._client.edit_inline_text(self._mid, full)
        except Exception:
            pass

    async def report_error(self, stage: str, error: Exception) -> None:
        await self._client.edit_inline_text(
            self._mid,
            f"{stage}错误: \n```\n{error}```",
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        await asyncio.sleep(5)
        # 恢复为 caption
        await self._client.edit_inline_text(
            self._mid,
            self._caption,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )

    async def dismiss(self) -> None:
        pass


def build_cached_inline_results(entry: CacheEntry, raw_url: str) -> list:
    """有 file_id 缓存时，构建 cached 类型的 inline 结果（Telegram 服务端直发）"""
    title = entry.parse_result.title or "无标题"
    content = entry.parse_result.content
    caption = build_caption_by_str(title, content, raw_url, entry.telegraph_url)

    # 富文本
    if entry.telegraph_url:
        return [
            InlineQueryResultArticle(
                title=title,
                input_message_content=InputTextMessageContent(
                    caption,
                    link_preview_options=LinkPreviewOptions(show_above_text=True),
                ),
            )
        ]

    flat_media = [x for sub in entry.media for x in (sub if isinstance(sub, list) else [sub])]
    results = []

    for m in flat_media:
        match m.type:
            case CacheMediaType.PHOTO:
                results.append(
                    InlineQueryResultCachedPhoto(
                        photo_file_id=m.file_id,
                        caption=caption,
                        description=content,
                    )
                )
            case CacheMediaType.VIDEO:
                results.append(
                    InlineQueryResultCachedVideo(
                        video_file_id=m.file_id,
                        caption=caption,
                        description=content,
                        title=title,
                    )
                )
            case CacheMediaType.ANIMATION:
                results.append(
                    InlineQueryResultCachedDocument(
                        document_file_id=m.file_id,
                        caption=caption,
                        description=content,
                        title=title,
                    )
                )
            case CacheMediaType.DOCUMENT:
                results.append(
                    InlineQueryResultCachedDocument(
                        document_file_id=m.file_id,
                        caption=caption,
                        description=content,
                        title=title,
                    )
                )

    return results


async def build_inline_results(parse_result: AnyParseResult, cli: Client) -> list:
    """根据解析结果构建内联查询结果列表"""
    logger.debug(f"构建 inline 结果: type={parse_result.type}, title={parse_result.title}")
    title = parse_result.title or "无标题"
    media_list = parse_result.media if isinstance(parse_result.media, list) else [parse_result.media]
    reply_markup = Ikm([[Ikb("原链接", url=parse_result.raw_url)]])

    results = []

    # ── 富文本直接 telegraph 发送 ──
    if parse_result.type == PostType.RICHTEXT:
        url = await create_richtext_telegraph(cli, parse_result)
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

    logger.debug(f"inline 结果构建完成: count={len(results)}")
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
    logger.debug(f"inline 查询触发: query={inline_query.query}, from_user={inline_query.from_user.id}")
    url = inline_query.query
    raw_url = await ParseService().get_raw_url(url)

    inline_query.query = raw_url

    # 先查 file_id 缓存 → 如有则用 cached 类型直接返回
    cached = await persistent_cache.get(raw_url)
    if cached:
        logger.debug("inline: file_id 缓存命中, 构建 cached 结果")
        results = build_cached_inline_results(cached, raw_url)
        return await inline_query.answer(results[:50], cache_time=60)

    # 查内存解析缓存
    parse_result = await parse_cache.get(raw_url)
    if parse_result is None:
        parse_result = await ParseService().parse(raw_url)
        await parse_cache.set(raw_url, parse_result)

    results = await build_inline_results(parse_result, cli)
    logger.debug(f"inline 查询完成, 返回 {len(results)} 个结果")
    return await inline_query.answer(results[:50], cache_time=0)


@Client.on_chosen_inline_result()
async def inline_result_download(client: Client, chosen_result: ChosenInlineResult):
    if not chosen_result.result_id.startswith("download_"):
        return

    media_index = int(chosen_result.result_id.split("_")[1])
    inline_message_id = chosen_result.inline_message_id
    query = chosen_result.query
    logger.debug(f"inline 下载触发: media_index={media_index}, query={query}")

    cached_result = await parse_cache.get(query)
    logger.debug(f"缓存命中: {cached_result is not None}")

    caption = build_caption(cached_result) if cached_result else ""
    reporter = InlineStatusReporter(client, inline_message_id, caption)

    pipeline = ParsePipeline(query, reporter, parse_result=cached_result)
    result = await pipeline.run()
    if result is None:
        return

    parse_result = result.parse_result
    caption = build_caption(parse_result)

    # ── 上传 ──
    await reporter.report("**▎上 传 中...**")

    processed = result.processed_list[media_index]
    video_ref = parse_result.media[media_index] if isinstance(parse_result.media, list) else parse_result.media

    try:
        file_paths = processed.output_paths or [processed.source.path]
        file_path_str = str(file_paths[0])
        logger.debug(f"inline 上传文件: {file_path_str}")
        width, height = processed.source.width, processed.source.height
        duration = getattr(processed.source, "duration", 0)

        if processed.output_paths:
            media_info = MediaInfoReader.read(file_path_str)
            width, height, duration = media_info.width, media_info.height, media_info.duration

        sent = await client.edit_inline_media(
            inline_message_id,
            media=InputMediaVideo(
                file_path_str,
                caption=caption,
                video_cover=video_ref.thumb_url if video_ref else None,
                duration=duration or 0,
                width=width or 0,
                height=height or 0,
                supports_streaming=True,
            ),
        )
        # 写入 file_id 缓存 (inline 上传后)
        if sent and hasattr(sent, "video") and sent.video:
            await persistent_cache.set(
                query,
                CacheEntry(
                    parse_result=CacheParseResult(title=parse_result.title, content=parse_result.content),
                    media=[CacheMedia(type=CacheMediaType.VIDEO, file_id=sent.video.file_id)],
                ),
            )
    except Exception as e:
        logger.debug(f"inline 上传失败: {e}")
        await reporter.report_error("上传", e)
    finally:
        logger.debug("inline 下载任务完成, 清理资源")
        result.cleanup()
