from collections.abc import Sequence

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
    InlineQueryResult,
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

from db import get_session
from i18n import t_
from log import logger
from plugins.filters import platform_filter
from plugins.helpers import (
    build_caption,
    build_caption_by_str,
    build_start_text,
    create_richtext_telegraph,
)
from plugins.parse.reporters import InlineStatusReporter
from repo.settings import SettingsConfig
from services import ParseService, SettingsService, UserService
from services.cache import CacheEntry, CacheMediaType, parse_cache, persistent_cache
from services.media import resolve_media_info
from services.pipeline import ParsePipeline
from utils.helpers import to_list, with_request_id

logger = logger.bind(name="InlineParse")

SEARCH_ICON = "https://i.imgloc.com/2023/06/15/Vbfazk.png"
DEFAULT_PARSE_RESULT_THUMB_URL = "https://telegra.ph/file/cdfdb65b83a4b7b2b6078.png"
LINK_ICON_URL = "https://i.iij.li/i/20260627/6a3fb12066abb.png"
LINK_ICON_WIDTH = 72
LINK_ICON_HEIGHT = 72


@Client.on_inline_query(~platform_filter(False))
async def inline_parse_tip(_: Client, inline_query: InlineQuery) -> None:
    async with get_session() as session:
        lang = await UserService(session).get_lang(inline_query.from_user.id)
    _t = t_[lang]
    results: list[InlineQueryResult] = [
        InlineQueryResultArticle(
            title=_t("聚合解析"),
            description=_t("请在聊天框输入链接"),
            input_message_content=InputTextMessageContent(
                build_start_text()[lang], link_preview_options=LinkPreviewOptions(is_disabled=True)
            ),
            thumb_url=SEARCH_ICON,
        )
    ]
    await inline_query.answer(results=results, cache_time=1)


@Client.on_inline_query(platform_filter(False))
@with_request_id
async def call_inline_parse(cli: Client, inline_query: InlineQuery) -> None:
    logger.info(f"收到内联解析请求: query={inline_query.query}, from_user={inline_query.from_user.id}")
    raw_url = await ParseService().get_raw_url(inline_query.query)
    async with get_session() as session:
        lang = await UserService(session).get_lang(inline_query.from_user.id)
        config = await SettingsService(session).get_config_by_user(inline_query.from_user.id)
    if cached := await persistent_cache.get(raw_url):
        logger.debug("inline: 缓存命中, 构建 cached 结果")
        results = build_cached_inline_results(cached, raw_url, lang, config)
        await inline_query.answer(results[:50], cache_time=60)
        return

    parse_result = await parse_cache.get(raw_url)
    if parse_result is None:
        parse_result = await ParseService().parse(inline_query.query)
        await parse_cache.set(raw_url, parse_result)

    results = await build_inline_results(parse_result, cli, lang, config)
    logger.debug(f"inline 查询完成, 返回 {len(results)} 个结果")
    await inline_query.answer(results[:50], cache_time=0)


@Client.on_chosen_inline_result()
@with_request_id
async def inline_result_download(cli: Client, chosen_result: ChosenInlineResult) -> None:
    if not chosen_result.result_id.startswith("download_"):
        return

    async with get_session() as session:
        lang = await UserService(session).get_lang(chosen_result.from_user.id)
        config = await SettingsService(session).get_config_by_user(chosen_result.from_user.id)
        _t = t_[lang]
    media_index = int(chosen_result.result_id.split("_")[1])
    inline_message_id = chosen_result.inline_message_id
    if inline_message_id is None:
        return
    query = chosen_result.query
    logger.debug(f"inline 下载触发: media_index={media_index}, query={query}")
    raw_url = await ParseService().get_raw_url(query)

    cached_result = await parse_cache.get(raw_url)
    logger.debug(f"缓存命中: {cached_result is not None}")

    caption = build_caption(cached_result, config=config) if cached_result else ""
    reporter = InlineStatusReporter(cli, inline_message_id, caption, t=_t, user_config=config)
    with ParsePipeline(query, raw_url, reporter, parse_result=cached_result, singleflight=False, t=_t) as pipeline:
        if (result := await pipeline.run()) is None:
            return

        parse_result = result.parse_result
        caption = build_caption(parse_result, config=config)

        # ── 上传 ──
        await reporter.report(_t("上 传 中..."))

        processed = result.processed_list[media_index]
        video_ref = parse_result.media[media_index] if isinstance(parse_result.media, Sequence) else parse_result.media

        try:
            file_paths = processed.output_paths or [processed.source.path]
            file_path_str = str(file_paths[0])
            logger.debug(f"inline 上传文件: {file_path_str}")
            width, height, duration = resolve_media_info(processed, file_path_str)

            video_cover = str(video_ref.thumb_url) if video_ref and video_ref.thumb_url else None
            media = (
                InputMediaVideo(
                    file_path_str,
                    caption=caption,
                    video_cover=video_cover,
                    duration=duration or 0,
                    width=width or 0,
                    height=height or 0,
                    supports_streaming=True,
                )
                if video_cover
                else InputMediaVideo(
                    file_path_str,
                    caption=caption,
                    duration=duration or 0,
                    width=width or 0,
                    height=height or 0,
                    supports_streaming=True,
                )
            )
            await cli.edit_inline_media(inline_message_id, media=media)
        except Exception as e:
            logger.opt(exception=e).debug("详细堆栈")
            logger.error(f"inline 上传失败: {e}")
            await reporter.report_error(_t("上传"), e)
        finally:
            logger.debug("inline 下载任务完成")


def build_cached_inline_results(
    entry: CacheEntry, raw_url: str, lang: str, config: SettingsConfig
) -> list[InlineQueryResult]:
    """有 file_id 缓存时，构建 cached 类型的 inline 结果（Telegram 服务端直发）"""
    _t = t_[lang]

    content = entry.parse_result.content
    caption = build_caption_by_str(
        entry.parse_result.title,
        content,
        raw_url,
        entry.telegraph_url,
        hide_source=config.hide_source,
        hide_title=config.hide_title,
        hide_desc=config.hide_desc,
    )
    title = entry.parse_result.title or "-"

    results: list[InlineQueryResult] = []

    if config.enable_inline_raw_url:
        results.append(
            InlineQueryResultArticle(
                title=_t("原始链接"),
                description=raw_url,
                input_message_content=InputTextMessageContent(
                    raw_url, link_preview_options=LinkPreviewOptions(is_disabled=True)
                ),
                thumb_url=LINK_ICON_URL,
                thumb_width=LINK_ICON_WIDTH,
                thumb_height=LINK_ICON_HEIGHT,
            )
        )

    # 富文本
    if entry.telegraph_url:
        results.append(
            InlineQueryResultArticle(
                title=title,
                input_message_content=InputTextMessageContent(
                    caption,
                    link_preview_options=LinkPreviewOptions(show_above_text=True),
                ),
            )
        )
        return results

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


async def build_inline_results(
    parse_result: AnyParseResult, cli: Client, lang: str, config: SettingsConfig
) -> list[InlineQueryResult]:
    """根据解析结果构建内联查询结果列表"""
    logger.debug(f"构建 inline 结果: type={parse_result.type}, title={parse_result.title}")
    _t = t_[lang]

    title = parse_result.title or "-"
    media_list = to_list(parse_result.media)
    reply_markup = Ikm([[Ikb(_t("原链接"), url=parse_result.raw_url)]])

    results: list[InlineQueryResult] = []
    if config.enable_inline_raw_url:
        results.append(
            InlineQueryResultArticle(
                title=_t("原始链接"),
                description=parse_result.raw_url,
                input_message_content=InputTextMessageContent(
                    parse_result.raw_url, link_preview_options=LinkPreviewOptions(is_disabled=True)
                ),
                thumb_url=LINK_ICON_URL,
                thumb_width=LINK_ICON_WIDTH,
                thumb_height=LINK_ICON_HEIGHT,
            )
        )

    # ── 富文本直接 telegraph 发送 ──
    if parse_result.type == PostType.RICHTEXT:
        url = await create_richtext_telegraph(cli, parse_result)
        caption = build_caption(parse_result, url, config=config)
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

    caption = build_caption(parse_result, config=config)

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
                    media_ref.thumb_url or DEFAULT_PARSE_RESULT_THUMB_URL,
                    photo_width=media_ref.width,
                    photo_height=media_ref.height,
                    id=f"download_{index}",
                    title=title,
                    caption=caption,
                    reply_markup=reply_markup,
                )
            )
        elif isinstance(media_ref, AniRef):
            if media_ref.ext != "gif":
                results.append(
                    InlineQueryResultVideo(
                        media_ref.url,
                        media_ref.thumb_url or DEFAULT_PARSE_RESULT_THUMB_URL,
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
