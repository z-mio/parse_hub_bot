import asyncio

from parsehub.types import (
    AniFile,
    AnyMediaRef,
    ImageFile,
    LivePhotoFile,
    PostType,
    VideoFile,
)
from parsehub.utils.media_info import MediaInfoReader
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
from plugins.helpers import build_caption, build_caption_by_str, create_richtext_telegraph
from services import ParseService
from services.cache import CacheEntry, CacheMedia, CacheMediaType, CacheParseResult, parse_cache, persistent_cache
from services.pipeline import ParsePipeline, StatusReporter

logger = logger.bind(name="Parse")


class MessageStatusReporter(StatusReporter):
    """基于 Telegram Message 的状态报告器"""

    def __init__(self, user_msg: Message):
        self._user_msg = user_msg
        self._msg = None

    async def report(self, text: str) -> None:
        await self.edit_text(text)

    async def report_error(self, stage: str, error: Exception) -> None:
        await self.edit_text(
            f"{stage}错误: \n```\n{error}```",
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        await asyncio.sleep(5)
        await self._msg.delete()

    async def dismiss(self) -> None:
        if self._msg:
            await self._msg.delete()

    async def edit_text(self, text: str, **kwargs):
        if self._msg is None:
            self._msg = await self._user_msg.reply_text(text, **kwargs)
        else:
            if self._msg.text != text:
                await self._msg.edit_text(text, **kwargs)
                self._msg.text = text


@Client.on_message((filters.text | filters.caption) & platform_filter)
async def text_jx(cli: Client, msg: Message):
    url = msg.text or msg.caption
    await handle_parse(cli, msg, url)


@Client.on_message(filters.command(["jx"]))
async def cmd_jx(cli: Client, msg: Message):
    url = msg.command[1] if msg.command[1:] else ""

    if not url and msg.reply_to_message:
        url = msg.reply_to_message.text or msg.reply_to_message.caption or ""

    if not url:
        await msg.reply_text("请加上链接或回复一条消息")
        return

    await handle_parse(cli, msg, url)


async def handle_parse(cli: Client, msg: Message, url: str):
    logger.debug(f"收到解析请求: url={url}, chat_id={msg.chat.id}, msg_id={msg.id}")
    raw_url = await ParseService().get_raw_url(url)

    if cached := await persistent_cache.get(raw_url):
        logger.debug(f"file_id 缓存命中, 直接发送: raw_url={raw_url}")
        await _send_cached(msg, cached, raw_url)
        return

    reporter = MessageStatusReporter(msg)
    cached_parse_result = await parse_cache.get(raw_url)
    pipeline = ParsePipeline(raw_url, reporter, parse_result=cached_parse_result)

    if (result := await pipeline.run()) is None:
        logger.debug(f"Pipeline 返回 None, 跳过后续处理: raw_url={raw_url}")
        return

    parse_result = result.parse_result
    await parse_cache.set(raw_url, parse_result)

    # ── 富文本 → Telegraph ──
    if parse_result.type == PostType.RICHTEXT:
        logger.debug(f"富文本类型, 创建 Telegraph 页面: title={parse_result.title}")
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

    # ── 上传 ──
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

    await reporter.dismiss()


async def _send_media(msg: Message, parse_result, processed_list, caption: str) -> CacheEntry | None:
    logger.debug(f"构建媒体列表: processed_count={len(processed_list)}")
    input_photos_videos: list[InputMediaPhoto | InputMediaVideo] = []
    input_animations: list[InputMediaAnimation] = []

    media_refs: list[AnyMediaRef] = parse_result.media if isinstance(parse_result.media, list) else [parse_result.media]

    for media_ref, processed in zip(media_refs, processed_list, strict=False):
        file_paths = processed.output_paths or [processed.source.path]
        for file_path in file_paths:
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

            match processed.source:
                case ImageFile():
                    input_photos_videos.append(InputMediaPhoto(media=file_path_str))
                case AniFile():
                    input_animations.append(InputMediaAnimation(media=file_path_str))
                case VideoFile():
                    input_photos_videos.append(
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
                    input_photos_videos.append(
                        InputMediaVideo(
                            media=processed.source.video_path,
                            video_cover=file_path_str,
                            duration=duration,
                            width=width,
                            height=height,
                            supports_streaming=True,
                        )
                    )

    all_media = input_animations + input_photos_videos
    logger.debug(f"媒体分类完成: animations={len(input_animations)}, photos_videos={len(input_photos_videos)}")

    media_list: list[CacheMedia] = []
    if len(all_media) == 1:
        logger.debug("单媒体模式发送")
        try:
            if input_animations:
                sent = await msg.reply_animation(input_animations[0].media, caption=caption)
                media_list.append(CacheMedia(type=CacheMediaType.ANIMATION, file_id=sent.animation.file_id))
            else:
                single = input_photos_videos[0]
                match single:
                    case InputMediaPhoto():
                        sent = await msg.reply_photo(single.media, caption=caption)
                        media_list.append(CacheMedia(type=CacheMediaType.PHOTO, file_id=sent.photo.file_id))
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
                        media_list.append(
                            CacheMedia(
                                type=CacheMediaType.VIDEO,
                                file_id=sent.video.file_id,
                                cover_file_id=sent.video.video_cover.file_id if sent.video.video_cover else None,
                            )
                        )
        except Exception as e:
            logger.opt(exception=e).debug("详细堆栈")
            logger.warning(f"上传失败 {e}, 使用兼容模式上传")
            await msg.reply_document(all_media[0].media, caption=caption)
    else:
        logger.debug(f"多媒体模式发送: total={len(all_media)}")
        for ani in input_animations:
            sent = await msg.reply_animation(ani.media)
            media_list.append(CacheMedia(type=CacheMediaType.ANIMATION, file_id=sent.animation.file_id))
        try:
            for i in range(0, len(input_photos_videos), 10):
                batch = input_photos_videos[i : i + 10]
                sent_msgs = await msg.reply_media_group(batch)
                for m in sent_msgs:
                    if m.photo:
                        media_list.append(CacheMedia(type=CacheMediaType.PHOTO, file_id=m.photo.file_id))
                    elif m.video:
                        media_list.append(
                            CacheMedia(
                                type=CacheMediaType.VIDEO,
                                file_id=m.video.file_id,
                                cover_file_id=m.video.video_cover.file_id if m.video.video_cover else None,
                            )
                        )
                    elif m.document:
                        media_list.append(CacheMedia(type=CacheMediaType.DOCUMENT, file_id=m.document.file_id))
        except Exception as e:
            logger.opt(exception=e).debug("详细堆栈")
            logger.warning(f"上传失败 {e}, 使用兼容模式上传")
            input_documents = [InputMediaDocument(media=item.media) for item in input_photos_videos]
            for i in range(0, len(input_documents), 10):
                batch = input_documents[i : i + 10]
                await msg.reply_media_group(batch)  # type: ignore
        await msg.reply_text(
            caption,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )

    return CacheEntry(
        parse_result=CacheParseResult(title=parse_result.title, content=parse_result.content), media=media_list
    )


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
        m: CacheMedia = entry.media[0]
        match m.type:
            case CacheMediaType.PHOTO:
                await msg.reply_photo(m.file_id, caption=caption)
            case CacheMediaType.VIDEO:
                await msg.reply_video(m.file_id, caption=caption, supports_streaming=True, video_cover=m.cover_file_id)
            case CacheMediaType.ANIMATION:
                await msg.reply_animation(m.file_id, caption=caption)
            case CacheMediaType.DOCUMENT:
                await msg.reply_document(m.file_id, caption=caption)
    else:
        animations = [sub for sub in entry.media if sub.type == CacheMediaType.ANIMATION]
        others = [sub for sub in entry.media if sub.type != CacheMediaType.ANIMATION]

        for m in animations:
            await msg.reply_animation(m.file_id)

        if others:
            media_group = []
            for m in others:
                match m.type:
                    case CacheMediaType.PHOTO:
                        media_group.append(InputMediaPhoto(media=m.file_id))
                    case CacheMediaType.VIDEO:
                        media_group.append(
                            InputMediaVideo(media=m.file_id, supports_streaming=True, video_cover=m.cover_file_id)
                        )
                    case CacheMediaType.DOCUMENT:
                        media_group.append(InputMediaDocument(media=m.file_id))

            for i in range(0, len(media_group), 10):
                await msg.reply_media_group(media_group[i : i + 10])

        await msg.reply_text(
            caption,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
