import asyncio
from typing import Literal

from parsehub.types import (
    AniFile,
    AnyMediaRef,
    ImageFile,
    LivePhotoFile,
    PostType,
    VideoFile,
)
from pyrogram import Client, enums, filters
from pyrogram.types import (
    InputMediaAnimation,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    LinkPreviewOptions,
    Message,
)

from log import logger
from plugins.filters import platform_filter
from plugins.helpers import (
    ProcessedMedia,
    build_caption,
    build_caption_by_str,
    create_richtext_telegraph,
    resolve_media_info,
)
from services import ParseService
from services.cache import CacheEntry, CacheMedia, CacheMediaType, CacheParseResult, parse_cache, persistent_cache
from services.pipeline import ParsePipeline, PipelineResult, StatusReporter
from utils.helpers import to_list

logger = logger.bind(name="Parse")
SKIP_DOWNLOAD_THRESHOLD = 0


class MessageStatusReporter(StatusReporter):
    """基于 Telegram Message 的状态报告器"""

    def __init__(self, user_msg: Message):
        self._user_msg = user_msg
        self._msg = None

    async def report(self, text: str) -> None:
        await self._edit_text(text)

    async def report_error(self, stage: str, error: Exception) -> None:
        await self._edit_text(
            f"**▎{stage}错误:** \n```\n{error}```",
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        await asyncio.sleep(5)
        await self._msg.delete()

    async def dismiss(self) -> None:
        if self._msg:
            await self._msg.delete()

    async def _edit_text(self, text: str, **kwargs):
        if self._msg is None:
            self._msg = await self._user_msg.reply_text(text, **kwargs)
        else:
            if self._msg.text != text:
                await self._msg.edit_text(text, **kwargs)
                self._msg.text = text


# ── Handler ──────────────────────────────────────────────────────────


@Client.on_message(filters.command(["jx", "raw"]) | ((filters.text | filters.caption) & platform_filter))
async def jx(cli: Client, msg: Message):
    mode = "preview"
    if msg.command:
        if msg.command[0] == "raw":
            mode = "raw"
        url = " ".join(msg.command[1:]) if msg.command[1:] else ""
        if not url and msg.reply_to_message:
            url = msg.reply_to_message.text or msg.reply_to_message.caption or ""
        if not url:
            await msg.reply_text("**▎请加上链接或回复一条消息**")
            return
    else:
        url = msg.text or msg.caption

    await handle_parse(cli, msg, url, mode)


# ── 主流程 ───────────────────────────────────────────────────────────


async def handle_parse(cli: Client, msg: Message, url: str, mode: Literal["raw", "preview"] | str = "preview") -> None:
    logger.debug(f"收到解析请求: url={url}, chat_id={msg.chat.id}, msg_id={msg.id}, mode={mode}")
    is_raw_mode = mode == "raw"
    raw_url = await ParseService().get_raw_url(url)

    if not is_raw_mode and (cached := await persistent_cache.get(raw_url)):
        logger.debug(f"file_id 缓存命中, 直接发送: raw_url={raw_url}")
        await _send_cached(msg, cached, raw_url)
        return

    reporter = MessageStatusReporter(msg)
    cached_parse_result = await parse_cache.get(raw_url)
    pipeline = ParsePipeline(url, reporter, parse_result=cached_parse_result)

    singleflight = False if is_raw_mode else True
    if (
        result := await pipeline.run(
            singleflight=singleflight,
            skip_media_processing=is_raw_mode,
            skip_download_threshold=SKIP_DOWNLOAD_THRESHOLD,
        )
    ) is None:
        if pipeline.waited:
            logger.debug(f"Singleflight 等待完成, 重新检查缓存: raw_url={raw_url}")
            if cached := await persistent_cache.get(raw_url):
                await _send_cached(msg, cached, raw_url)
            else:
                await handle_parse(cli, msg, url)
                return
        else:
            logger.debug(f"Pipeline 返回 None, 跳过后续处理: raw_url={raw_url}")
        return

    parse_result = result.parse_result
    await parse_cache.set(raw_url, parse_result)

    if mode == "raw":
        await _send_raw(msg, result, reporter)
        return

    # ── 富文本 → Telegraph ──
    if parse_result.type == PostType.RICHTEXT:
        logger.debug(f"富文本类型, 创建 Telegraph 页面: title={parse_result.title}")
        try:
            await msg.reply_chat_action(enums.ChatAction.UPLOAD_PHOTO)
            ph_url = await create_richtext_telegraph(cli, parse_result)
            logger.debug(f"Telegraph 页面创建完成: {ph_url}")
            caption = build_caption(parse_result, ph_url)
            await msg.reply_text(
                caption,
                link_preview_options=LinkPreviewOptions(show_above_text=True),
            )
            await persistent_cache.set(
                raw_url,
                CacheEntry(
                    parse_result=CacheParseResult(title=parse_result.title, content=parse_result.content),
                    telegraph_url=ph_url,
                ),
            )
            await reporter.dismiss()
            return
        finally:
            pipeline.finish()

    # ── 上传媒体 ──
    logger.debug(f"开始上传媒体: media_count={len(result.processed_list)}")
    await reporter.report("**▎上 传 中...**")
    try:
        await msg.reply_chat_action(enums.ChatAction.UPLOAD_PHOTO)
        caption = build_caption(parse_result)

        if not result.processed_list:
            logger.debug("无媒体文件, 仅发送文本")
            await msg.reply_text(
                caption,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
            await reporter.dismiss()
            cache_entry = CacheEntry(
                parse_result=CacheParseResult(title=parse_result.title, content=parse_result.content)
            )
        else:
            cache_entry = await _send_media(msg, parse_result, result.processed_list, caption)

        if cache_entry:
            await persistent_cache.set(raw_url, cache_entry)
    except Exception as e:
        logger.opt(exception=e).debug("详细堆栈")
        logger.error(f"上传失败: {e}")
        await reporter.report_error("上传", e)
        return
    finally:
        logger.debug("清理资源")
        result.cleanup()
        pipeline.finish()

    await reporter.dismiss()


# ── 构建 InputMedia ──────────────────────────────────────────────────


def _build_input_media(
    media_refs: list[AnyMediaRef],
    processed_list: list[ProcessedMedia],
) -> tuple[list[InputMediaPhoto | InputMediaVideo], list[InputMediaAnimation]]:
    """根据处理结果和媒体引用构建 Telegram InputMedia 列表。

    Returns:
        (photos_videos, animations) 两类媒体列表
    """
    photos_videos: list[InputMediaPhoto | InputMediaVideo] = []
    animations: list[InputMediaAnimation] = []

    for media_ref, processed in zip(media_refs, processed_list, strict=False):
        file_paths = processed.output_paths or [processed.source.path]
        for file_path in file_paths:
            file_path_str = str(file_path)
            width, height, duration = resolve_media_info(processed, file_path_str)

            match processed.source:
                case ImageFile():
                    photos_videos.append(InputMediaPhoto(media=file_path_str))
                case AniFile():
                    animations.append(InputMediaAnimation(media=file_path_str))
                case VideoFile():
                    photos_videos.append(
                        InputMediaVideo(
                            media=file_path_str,
                            video_cover=media_ref.thumb_url,
                            duration=duration,
                            width=width,
                            height=height,
                            supports_streaming=True,
                        )
                    )
                case LivePhotoFile():
                    photos_videos.append(
                        InputMediaVideo(
                            media=processed.source.video_path,
                            video_cover=file_path_str,
                            duration=duration,
                            width=width,
                            height=height,
                            supports_streaming=True,
                        )
                    )

    return photos_videos, animations


# ── 缓存条目构建 ─────────────────────────────────────────────────────


def _cache_media_from_message(m: Message) -> CacheMedia | None:
    """从已发送的 Telegram Message 提取 CacheMedia。"""
    if m.photo:
        return CacheMedia(type=CacheMediaType.PHOTO, file_id=m.photo.file_id)
    if m.video:
        return CacheMedia(
            type=CacheMediaType.VIDEO,
            file_id=m.video.file_id,
            cover_file_id=m.video.video_cover.file_id if m.video.video_cover else None,
        )
    if m.animation:
        return CacheMedia(type=CacheMediaType.ANIMATION, file_id=m.animation.file_id)
    if m.document:
        return CacheMedia(type=CacheMediaType.DOCUMENT, file_id=m.document.file_id)
    return None


def _make_cache_entry(parse_result, media_list: list[CacheMedia]) -> CacheEntry:
    return CacheEntry(
        parse_result=CacheParseResult(title=parse_result.title, content=parse_result.content),
        media=media_list,
    )


# ── Raw 模式上传 ──────────────────────────────────────────────────────


async def _send_raw(
    msg: Message,
    result: PipelineResult,
    reporter: MessageStatusReporter,
) -> None:
    """Raw 模式：将文件以原始文档形式上传。"""
    logger.debug("Raw 模式, 直接上传文件")
    await reporter.report("**▎上 传 中...**")
    try:
        await msg.reply_chat_action(enums.ChatAction.UPLOAD_DOCUMENT)
        caption = build_caption(result.parse_result)

        if not result.processed_list:
            logger.debug("无媒体文件, 仅发送文本")
            await msg.reply_text(
                caption,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
        else:
            all_docs: list[InputMediaDocument] = []
            livephoto_videos: dict[int, InputMediaDocument] = {}
            for idx, processed in enumerate(result.processed_list):
                # raw 模式下 processed.output_paths 只有一个文件
                file_path = processed.output_paths[0]
                all_docs.append(InputMediaDocument(media=str(file_path)))
                if isinstance(processed.source, LivePhotoFile):
                    livephoto_videos[idx] = InputMediaDocument(media=str(processed.source.video_path))
            if len(all_docs) == 1:
                m = await msg.reply_document(all_docs[0].media, caption=caption, force_document=True)
                await m.reply_document(livephoto_videos[0].media, force_document=True)
            else:
                msgs: list[Message] = []
                for i in range(0, len(all_docs), 10):
                    batch = all_docs[i : i + 10]
                    mg = await msg.reply_media_group(batch)  # type: ignore
                    msgs.extend(mg)
                    await asyncio.sleep(0.5)
                if livephoto_videos:
                    for idx, m in livephoto_videos.items():
                        await msgs[idx].reply_document(m.media, force_document=True)
                        await asyncio.sleep(0.5)
                await msg.reply_text(
                    caption,
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                )

    except Exception as e:
        logger.opt(exception=e).debug("详细堆栈")
        logger.error(f"Raw 模式上传失败: {e}")
        await reporter.report_error("上传", e)
        return
    finally:
        logger.debug("清理资源")
        result.cleanup()

    await reporter.dismiss()


# ── 发送媒体 ─────────────────────────────────────────────────────────


async def _send_single(
    msg: Message,
    photos_videos: list[InputMediaPhoto | InputMediaVideo],
    animations: list[InputMediaAnimation],
    caption: str,
) -> list[CacheMedia] | None:
    """发送单个媒体，返回 CacheMedia 列表。上传失败时降级为 document。
    返回 None 表示不缓存
    """
    media_list: list[CacheMedia] = []
    all_media = animations + photos_videos

    try:
        if animations:
            sent = await msg.reply_animation(animations[0].media, caption=caption)
        else:
            single = photos_videos[0]
            match single:
                case InputMediaPhoto():
                    sent = await msg.reply_photo(single.media, caption=caption)
                case InputMediaVideo():
                    sent = await msg.reply_video(
                        single.media,
                        caption=caption,
                        video_cover=single.video_cover,
                        duration=single.duration,
                        width=single.width,
                        height=single.height,
                        supports_streaming=True,
                    )

        if sent and (cm := _cache_media_from_message(sent)):
            media_list.append(cm)
    except Exception as e:
        logger.warning(f"上传失败 {e}, 使用兼容模式上传")
        await msg.reply_document(all_media[0].media, caption=caption, force_document=True)
        return None

    return media_list


async def _send_multi(
    msg: Message,
    photos_videos: list[InputMediaPhoto | InputMediaVideo],
    animations: list[InputMediaAnimation],
    caption: str,
) -> list[CacheMedia] | None:
    """发送多个媒体（动图逐条、图片视频分批），返回 CacheMedia 列表。
    返回 None 表示不缓存
    """
    media_list: list[CacheMedia] = []
    not_cache = False

    for ani in animations:
        try:
            sent = await msg.reply_animation(ani.media)
        except Exception as e:
            logger.warning(f"上传失败 {e}, 使用兼容模式上传")
            not_cache = True
            await msg.reply_document(ani.media, force_document=True)
        else:
            media_list.append(CacheMedia(type=CacheMediaType.ANIMATION, file_id=sent.animation.file_id))
        await asyncio.sleep(0.5)

    try:
        for i in range(0, len(photos_videos), 10):
            batch = photos_videos[i : i + 10]
            sent_msgs = await msg.reply_media_group(batch)
            for m in sent_msgs:
                if cm := _cache_media_from_message(m):
                    media_list.append(cm)
    except Exception as e:
        logger.warning(f"上传失败 {e}, 使用兼容模式上传")
        input_documents = [InputMediaDocument(media=item.media) for item in photos_videos]
        for i in range(0, len(input_documents), 10):
            batch = input_documents[i : i + 10]
            await msg.reply_media_group(batch)  # type: ignore
            await asyncio.sleep(0.5)
        return None

    await msg.reply_text(
        caption,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )
    return None if not_cache else media_list


async def _send_media(
    msg: Message, parse_result, processed_list: list[ProcessedMedia], caption: str
) -> CacheEntry | None:
    """构建、发送媒体，并返回缓存条目。
    返回 None 表示不缓存
    """
    media_refs: list[AnyMediaRef] = to_list(parse_result.media)
    photos_videos, animations = _build_input_media(media_refs, processed_list)
    all_count = len(photos_videos) + len(animations)
    logger.debug(f"媒体分类完成: animations={len(animations)}, photos_videos={len(photos_videos)}")

    if all_count == 1:
        logger.debug("单媒体模式发送")
        media_list = await _send_single(msg, photos_videos, animations, caption)
    else:
        logger.debug(f"多媒体模式发送: total={all_count}")
        media_list = await _send_multi(msg, photos_videos, animations, caption)

    if media_list is None:
        return None
    return _make_cache_entry(parse_result, media_list)


# ── 缓存发送 ─────────────────────────────────────────────────────────


async def _send_cached(msg: Message, entry: CacheEntry, url: str):
    """从 file_id 缓存直接发送，跳过解析/下载/转码"""
    logger.debug(f"缓存发送: media={entry.media}")
    caption = build_caption_by_str(entry.parse_result.title, entry.parse_result.content, url, entry.telegraph_url)

    # 富文本类型
    if entry.telegraph_url:
        await msg.reply_text(
            caption,
            link_preview_options=LinkPreviewOptions(show_above_text=True),
        )
        return

    if not entry.media:
        await msg.reply_text(
            caption,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        return

    if len(entry.media) == 1:
        await _send_cached_single(msg, entry.media[0], caption)
    else:
        await _send_cached_multi(msg, entry.media, caption)


async def _send_cached_single(msg: Message, m: CacheMedia, caption: str) -> None:
    """从缓存发送单个媒体。"""
    match m.type:
        case CacheMediaType.PHOTO:
            await msg.reply_photo(m.file_id, caption=caption)
        case CacheMediaType.VIDEO:
            await msg.reply_video(m.file_id, caption=caption, supports_streaming=True, video_cover=m.cover_file_id)
        case CacheMediaType.ANIMATION:
            await msg.reply_animation(m.file_id, caption=caption)
        case CacheMediaType.DOCUMENT:
            await msg.reply_document(m.file_id, caption=caption, force_document=True)


async def _send_cached_multi(msg: Message, media: list[CacheMedia], caption: str) -> None:
    """从缓存发送多个媒体。"""
    animations = [m for m in media if m.type == CacheMediaType.ANIMATION]
    others = [m for m in media if m.type != CacheMediaType.ANIMATION]

    for m in animations:
        await msg.reply_animation(m.file_id)
        await asyncio.sleep(0.5)

    if others:
        media_group = _build_cached_media_group(others)
        for i in range(0, len(media_group), 10):
            await msg.reply_media_group(media_group[i : i + 10])
            await asyncio.sleep(0.5)

    await msg.reply_text(
        caption,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


def _build_cached_media_group(
    media: list[CacheMedia],
) -> list[InputMediaPhoto | InputMediaVideo | InputMediaDocument]:
    """从 CacheMedia 列表构建 Telegram media group。"""
    group: list[InputMediaPhoto | InputMediaVideo | InputMediaDocument] = []
    for m in media:
        match m.type:
            case CacheMediaType.PHOTO:
                group.append(InputMediaPhoto(media=m.file_id))
            case CacheMediaType.VIDEO:
                group.append(InputMediaVideo(media=m.file_id, supports_streaming=True, video_cover=m.cover_file_id))
            case CacheMediaType.DOCUMENT:
                group.append(InputMediaDocument(media=m.file_id))
    return group
