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
from plugins.helpers import build_caption, create_richtext_telegraph
from services.cache import CacheEntry, file_id_cache, parse_cache
from services.pipeline import ParsePipeline, StatusReporter
from utils.filters import platform_filter

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
        await self._msg.delete()

    async def edit_text(self, text: str, **kwargs):
        if self._msg is None:
            self._msg = await self._user_msg.reply_text(text, **kwargs)
        else:
            if self._msg.text != text:
                await self._msg.edit_text(text, **kwargs)
                self._msg.text = text


async def handle_parse(cli: Client, msg: Message, url: str):
    logger.debug(f"收到解析请求: url={url}, chat_id={msg.chat.id}, msg_id={msg.id}")

    # ── 检查 file_id 缓存 ──
    cached = await file_id_cache.get(url)
    if cached:
        logger.debug(f"file_id 缓存命中, 直接发送: url={url}")
        await _send_cached(msg, cached)
        return

    reporter = MessageStatusReporter(msg)

    # 检查内存中是否有解析结果缓存
    cached_parse_result = await parse_cache.get(url)

    pipeline = ParsePipeline(url, reporter, parse_result=cached_parse_result)
    result = await pipeline.run()

    if result is None:
        logger.debug(f"Pipeline 返回 None, 跳过后续处理: url={url}")
        return

    parse_result = result.parse_result

    # 写入解析结果到内存缓存 (供其他并发请求使用)
    await parse_cache.set(url, parse_result)

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
        # 缓存富文本的 telegraph_url
        await file_id_cache.set(
            url,
            CacheEntry(
                file_ids=[],
                caption=caption,
                title=parse_result.title,
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
            return

        cache_entry = await _send_media(msg, parse_result, result.processed_list, caption)
        # 写入 file_id 缓存
        if cache_entry:
            await file_id_cache.set(url, cache_entry)
    except Exception as e:
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

    file_ids: list[str | list[str]] = []
    media_types: list[str] = []

    if len(all_media) == 1:
        logger.debug("单媒体模式发送")
        try:
            if input_animations:
                sent = await msg.reply_animation(input_animations[0].media, caption=caption)
                file_ids.append(sent.animation.file_id)
                media_types.append("animation")
            else:
                single = input_photos_videos[0]
                match single:
                    case InputMediaPhoto():
                        sent = await msg.reply_photo(single.media, caption=caption)
                        file_ids.append(sent.photo.file_id)
                        media_types.append("photo")
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
                        file_ids.append(sent.video.file_id)
                        media_types.append("video")
        except Exception as e:
            logger.warning(f"上传失败 {e}, 使用兼容模式上传")
            sent = await msg.reply_document(all_media[0].media, caption=caption)
            file_ids.append(sent.document.file_id)
            media_types.append("document")
    else:
        logger.debug(f"多媒体模式发送: total={len(all_media)}")
        for ani in input_animations:
            sent = await msg.reply_animation(ani.media)
            file_ids.append(sent.animation.file_id)
            media_types.append("animation")
        try:
            for i in range(0, len(input_photos_videos), 10):
                batch = input_photos_videos[i : i + 10]
                sent_msgs = await msg.reply_media_group(batch)
                group_ids = []
                group_types = []
                for m in sent_msgs:
                    if m.photo:
                        group_ids.append(m.photo.file_id)
                        group_types.append("photo")
                    elif m.video:
                        group_ids.append(m.video.file_id)
                        group_types.append("video")
                    elif m.document:
                        group_ids.append(m.document.file_id)
                        group_types.append("document")
                file_ids.append(group_ids)
                media_types.append(group_types)
        except Exception as e:
            logger.warning(f"上传失败 {e}, 使用兼容模式上传")
            # 回退时清空之前收集的 photo/video ids, 重新收集 document ids
            file_ids = file_ids[: len(input_animations)]  # 保留 animation 部分
            media_types = media_types[: len(input_animations)]
            input_documents = [InputMediaDocument(media=item.media) for item in input_photos_videos]
            for i in range(0, len(input_documents), 10):
                batch = input_documents[i : i + 10]
                sent_msgs = await msg.reply_media_group(batch)
                group_ids = [m.document.file_id for m in sent_msgs]
                file_ids.append(group_ids)
                media_types.append(["document"] * len(group_ids))

        # 找到第一条消息来回复 caption
        # (这部分逻辑需要重新获取 sent_groups，但我们已经在上面处理了)
        # 为简化，使用 msg.reply_text
        await msg.reply_text(
            caption,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )

    return CacheEntry(
        file_ids=file_ids,
        caption=caption,
        media_types=media_types,
    )


async def _send_cached(msg: Message, entry: CacheEntry):
    """从 file_id 缓存直接发送，跳过解析/下载/转码"""
    logger.debug(f"缓存发送: file_ids={len(entry.file_ids)}, types={entry.media_types}")

    # 富文本类型 (只有 telegraph_url, 无 file_id)
    if entry.telegraph_url:
        await msg.reply_text(
            entry.caption,
            link_preview_options=LinkPreviewOptions(show_above_text=True),
        )
        return

    caption = entry.caption

    if not entry.file_ids:
        await msg.reply_text(
            caption,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        return

    # 展平: 将嵌套的 [group_ids] 和单个 id 统一处理
    flat_ids: list[str] = []
    flat_types: list[str] = []
    for fid, mtype in zip(entry.file_ids, entry.media_types, strict=False):
        if isinstance(fid, list):
            flat_ids.extend(fid)
            flat_types.extend(mtype if isinstance(mtype, list) else [mtype] * len(fid))
        else:
            flat_ids.append(fid)
            flat_types.append(mtype)

    if len(flat_ids) == 1:
        fid, mtype = flat_ids[0], flat_types[0]
        match mtype:
            case "photo":
                await msg.reply_photo(fid, caption=caption)
            case "video":
                await msg.reply_video(fid, caption=caption, supports_streaming=True)
            case "animation":
                await msg.reply_animation(fid, caption=caption)
            case "document":
                await msg.reply_document(fid, caption=caption)
    else:
        # 分离 animation 和 photo/video
        animations = [(fid, t) for fid, t in zip(flat_ids, flat_types, strict=False) if t == "animation"]
        others = [(fid, t) for fid, t in zip(flat_ids, flat_types, strict=False) if t != "animation"]

        for fid, _ in animations:
            await msg.reply_animation(fid)

        if others:
            media_group = []
            for fid, mtype in others:
                match mtype:
                    case "photo":
                        media_group.append(InputMediaPhoto(media=fid))
                    case "video":
                        media_group.append(InputMediaVideo(media=fid, supports_streaming=True))
                    case "document":
                        media_group.append(InputMediaDocument(media=fid))

            for i in range(0, len(media_group), 10):
                await msg.reply_media_group(media_group[i : i + 10])

        await msg.reply_text(
            caption,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        ) if len(flat_ids) > 1 else None


@Client.on_message((filters.text | filters.caption) & platform_filter)
async def text_jx(cli: Client, msg: Message):
    url = msg.text or msg.caption
    logger.debug(f"text_jx 触发: url={url}")
    await handle_parse(cli, msg, url)


@Client.on_message(filters.command(["jx"]))
async def cmd_jx(cli: Client, msg: Message):
    logger.debug(f"cmd_jx 触发: command={msg.command}")
    url = msg.command[1] if msg.command[1:] else ""

    if not url and msg.reply_to_message:
        url = msg.reply_to_message.text or msg.reply_to_message.caption or ""

    if not url:
        await msg.reply_text("请加上链接或回复一条消息")
        return

    await handle_parse(cli, msg, url)
