import asyncio

from parsehub import AnyParseResult
from parsehub.types import (
    AniRef,
    ImageRef,
    PostType,
    VideoRef,
)
from pyrogram import Client
from pyrogram.types import (
    ChosenInlineResult,
    InlineQuery,
    InlineQueryResultAnimation,
    InlineQueryResultArticle,
    InlineQueryResultCachedAnimation,
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
from plugins.filters import platform_filter
from plugins.helpers import build_caption, build_caption_by_str, create_richtext_telegraph, resolve_media_info
from plugins.start import get_supported_platforms
from services import ParseService
from services.cache import CacheEntry, CacheMediaType, parse_cache, persistent_cache
from services.pipeline import ParsePipeline, StatusReporter
from utils.helpers import to_list

logger = logger.bind(name="InlineParse")
DEFAULT_THUMB_URL = "https://telegra.ph/file/cdfdb65b83a4b7b2b6078.png"


class InlineStatusReporter(StatusReporter):
    """基于 inline_message_id 的状态报告器"""

    def __init__(self, cli: Client, inline_message_id: str, caption: str = ""):
        self._cli = cli
        self._mid = inline_message_id
        self._caption = caption
        self._last_text: str | None = None

    async def report(self, text: str) -> None:
        full = f"{self._caption}\n{text}" if self._caption else text
        if full == self._last_text:
            return
        self._last_text = full
        try:
            await self._cli.edit_inline_text(self._mid, full)
        except Exception:
            pass

    async def report_error(self, stage: str, error: Exception) -> None:
        await self._cli.edit_inline_text(
            self._mid,
            f"{stage}错误: \n```\n{error}```",
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        await asyncio.sleep(5)
        # 恢复为 caption
        await self._cli.edit_inline_text(
            self._mid,
            self._caption,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )

    async def dismiss(self) -> None:
        pass


def build_cached_inline_results(entry: CacheEntry, raw_url: str) -> list:
    """有 file_id 缓存时，构建 cached 类型的 inline 结果（Telegram 服务端直发）"""
    content = entry.parse_result.content
    caption = build_caption_by_str(entry.parse_result.title, content, raw_url, entry.telegraph_url)
    title = entry.parse_result.title or "无标题"

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

    results = []
    if not entry.media:
        results.append(
            InlineQueryResultArticle(
                title=title,
                description=content,
                input_message_content=InputTextMessageContent(
                    caption,
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                ),
            )
        )
        return results

    for m in entry.media:
        match m.type:
            case CacheMediaType.PHOTO:
                results.append(
                    InlineQueryResultCachedPhoto(
                        photo_file_id=m.file_id,
                        title=title,
                        caption=caption,
                        description=content,
                    )
                )
            case CacheMediaType.VIDEO:
                results.append(
                    InlineQueryResultCachedVideo(
                        video_file_id=m.file_id,
                        title=title,
                        caption=caption,
                        description=content,
                    )
                )
            case CacheMediaType.ANIMATION:
                results.append(
                    InlineQueryResultCachedAnimation(
                        animation_file_id=m.file_id,
                        title=title,
                        caption=caption,
                    )
                )
            case CacheMediaType.DOCUMENT:
                results.append(
                    InlineQueryResultCachedDocument(
                        document_file_id=m.file_id,
                        title=title,
                        caption=caption,
                        description=content,
                    )
                )

    return results


async def build_inline_results(parse_result: AnyParseResult, cli: Client) -> list:
    """根据解析结果构建内联查询结果列表"""
    logger.debug(f"构建 inline 结果: type={parse_result.type}, title={parse_result.title}")
    title = parse_result.title or "无标题"
    media_list = to_list(parse_result.media)
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
            )
        )
        return results

    for index, media_ref in enumerate(media_list):
        if isinstance(media_ref, ImageRef):
            results.append(
                InlineQueryResultPhoto(
                    media_ref.url,
                    thumb_url=media_ref.thumb_url,
                    photo_width=media_ref.width,
                    photo_height=media_ref.height,
                    caption=caption,
                    title=title,
                    description=parse_result.content,
                )
            )
        elif isinstance(media_ref, VideoRef):
            results.append(
                InlineQueryResultPhoto(
                    media_ref.thumb_url or DEFAULT_THUMB_URL,
                    photo_width=media_ref.width,
                    photo_height=media_ref.height,
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
    raw_url = await ParseService().get_raw_url(inline_query.query)

    if cached := await persistent_cache.get(raw_url):
        logger.debug("inline: 缓存命中, 构建 cached 结果")
        results = build_cached_inline_results(cached, raw_url)
        return await inline_query.answer(results[:50], cache_time=60)

    parse_result = await parse_cache.get(raw_url)
    if parse_result is None:
        parse_result = await ParseService().parse(inline_query.query)
        await parse_cache.set(raw_url, parse_result)

    results = await build_inline_results(parse_result, cli)
    logger.debug(f"inline 查询完成, 返回 {len(results)} 个结果")
    return await inline_query.answer(results[:50], cache_time=0)


@Client.on_chosen_inline_result()
async def inline_result_download(cli: Client, chosen_result: ChosenInlineResult):
    if not chosen_result.result_id.startswith("download_"):
        return

    media_index = int(chosen_result.result_id.split("_")[1])
    inline_message_id = chosen_result.inline_message_id
    query = chosen_result.query
    logger.debug(f"inline 下载触发: media_index={media_index}, query={query}")
    raw_url = await ParseService().get_raw_url(query)

    cached_result = await parse_cache.get(raw_url)
    logger.debug(f"缓存命中: {cached_result is not None}")

    caption = build_caption(cached_result) if cached_result else ""
    reporter = InlineStatusReporter(cli, inline_message_id, caption)
    pipeline = ParsePipeline(query, reporter, parse_result=cached_result)
    if (result := await pipeline.run(singleflight=False)) is None:
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
        width, height, duration = resolve_media_info(processed, file_path_str)

        await cli.edit_inline_media(
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
    except Exception as e:
        logger.opt(exception=e).debug("详细堆栈")
        logger.error(f"inline 上传失败: {e}")
        await reporter.report_error("上传", e)
    finally:
        logger.debug("inline 下载任务完成, 清理资源")
        result.cleanup()
